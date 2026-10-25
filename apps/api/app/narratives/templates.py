"""Deterministic narrative templates (English and Dutch) for the three viewer modes.

Used (a) by the deterministic policy planner when no live model is configured, and
(b) as the fallback whenever a live-model narrative fails verification. Every number is
taken from the evidence table, so these narratives always pass numeric grounding.
"""

from __future__ import annotations

from ..models.analysis import CounterfactualAnalysis
from ..models.common import Language, new_id, utcnow
from ..models.decisions import CandidateAction, DecisionPoint
from ..models.match import Player
from ..models.narrative import Narrative
from ..models.simulation import ActionResult, PairwiseComparison
from ..models.verification import EvidenceItem
from ..verification.evidence import action_keys, num, pct
from .templates_intl import INTL_LANGUAGES, build_intl_narratives

ASSUMPTIONS = {
    "en": [
        "Synthetic match and simplified physics: players move in straight lines at bounded speed after a reaction delay.",
        "Rebounds and set pieces are not modelled; a saved or blocked shot ends the rollout.",
        "Offside is approximated as a limit on runs, not adjudicated.",
        "Intervals capture Monte Carlo sampling error only, not model error. Not calibrated against real matches.",
    ],
    "nl": [
        "Synthetische wedstrijd en vereenvoudigde fysica: spelers bewegen na een reactietijd in rechte lijnen met begrensde snelheid.",
        "Rebounds en standaardsituaties worden niet gemodelleerd; een gestopt of geblokt schot beeindigt de simulatie.",
        "Buitenspel wordt benaderd als grens voor loopacties, niet beoordeeld.",
        "Intervallen geven alleen de Monte-Carlo-steekproeffout weer, niet de modelfout. Niet gekalibreerd op echte wedstrijden.",
    ],
}


def action_label(c: CandidateAction, roster: dict[str, Player], lang: Language) -> str:
    target = roster[c.target_player_id].short_name if c.target_player_id else None
    base = c.label.replace(" (actual)", "")
    if lang == "en":
        return base
    if c.action_type == "shoot":
        return "Schieten"
    if c.action_type == "pass" and target:
        return f"Steekpass naar {target}" if base.startswith("Through") else f"Pass naar {target}"
    mapping = {
        "Dribble towards goal": "Dribbel richting doel",
        "Dribble diagonally right": "Dribbel schuin naar rechts",
        "Dribble diagonally left": "Dribbel schuin naar links",
        "Dribble wide right": "Dribbel naar rechts buiten",
        "Dribble wide left": "Dribbel naar links buiten",
    }
    return mapping.get(base, "Dribbel")


def _noun(c: CandidateAction, lang: Language) -> str:
    if lang == "en":
        return {"shoot": "shot", "pass": "pass", "dribble": "dribble"}[c.action_type]
    return {"shoot": "schot", "pass": "pass", "dribble": "dribbel"}[c.action_type]


def _verb(c: CandidateAction, roster: dict[str, Player], lang: Language) -> str:
    t = roster[c.target_player_id].short_name if c.target_player_id else None
    if lang == "en":
        if c.action_type == "shoot":
            return "shoot"
        if c.action_type == "pass":
            return f"pass to {t}"
        return "dribble"
    if c.action_type == "shoot":
        return "te schieten"
    if c.action_type == "pass":
        return f"naar {t} te passen"
    return "door te dribbelen"


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _phrase(c: CandidateAction, roster: dict[str, Player], lang: Language) -> str:
    """Natural noun phrase for an option ('a pass to Mbeki-Larsen' / 'een pass naar Mbeki-Larsen')."""
    t = roster[c.target_player_id].short_name if c.target_player_id else None
    through = "-through-" in c.action_id
    if lang == "en":
        if c.action_type == "shoot":
            return "a shot"
        if c.action_type == "pass":
            return f"a through ball to {t}" if through else f"a pass to {t}"
        return "dribbling " + action_label(c, roster, lang).replace("Dribble ", "")
    if c.action_type == "shoot":
        return "een schot"
    if c.action_type == "pass":
        return f"een steekpass naar {t}" if through else f"een pass naar {t}"
    return "een dribbel" + action_label(c, roster, lang).replace("Dribbel", "", 1)


def _secondary_notes(cm: PairwiseComparison, actual: CandidateAction, lang: Language) -> list[str]:
    """Secondary differences whose 95% interval excludes zero (shots only when the actual was not a shot)."""
    notes: list[str] = []
    if actual.action_type == "shoot":
        # A shot ends the rollout, so shot/turnover rates are not comparable with the alternatives.
        return notes
    if actual.action_type != "shoot":
        if cm.diff_p_shot_ci95_low > 0:
            notes.append("creates a shot more often" if lang == "en" else "leidt het vaker tot een schot")
        elif cm.diff_p_shot_ci95_high < 0:
            notes.append("creates a shot less often" if lang == "en" else "leidt het minder vaak tot een schot")
    if cm.diff_p_turnover_ci95_low > 0:
        notes.append("loses the ball more often" if lang == "en" else "kost het vaker balverlies")
    elif cm.diff_p_turnover_ci95_high < 0:
        notes.append("loses the ball less often" if lang == "en" else "kost het minder vaak balverlies")
    return notes


def build_template_narratives(
    analysis: CounterfactualAnalysis,
    decision: DecisionPoint,
    roster: dict[str, Player],
    evidence: list[EvidenceItem],
    languages: list[Language] | None = None,
    generated_by: str = "policy-template",
) -> list[Narrative]:
    languages = languages or ["en", "nl"]
    sim = analysis.simulation
    assert sim is not None
    keys = action_keys(analysis)
    res: dict[str, ActionResult] = {r.action_id: r for r in sim.results}
    cand = {c.action_id: c for c in analysis.candidates}
    actual = next(c for c in analysis.candidates if c.is_actual)
    comps: dict[str, PairwiseComparison] = {c.action_id: c for c in sim.comparisons}
    alts = [c for c in analysis.candidates if not c.is_actual]
    best = max(alts, key=lambda c: (res[c.action_id].p_goal.value, comps[c.action_id].diff_p_goal))
    bc = comps[best.action_id]
    ra, rb = res[actual.action_id], res[best.action_id]
    n = sim.config.rollouts
    H = int(sim.config.horizon_s)
    minute = decision.match_clock_ms // 60000 + 1
    actor = roster[decision.actor_id].short_name
    dist = round(decision.features.distance_to_goal_m)
    refs_core = ["decision.minute", "decision.actor", "decision.distance_to_goal_m", "sim.rollouts", "sim.horizon_s",
                 f"results.{keys[actual.action_id]}.p_goal", f"results.{keys[best.action_id]}.p_goal",
                 f"comparisons.{keys[best.action_id]}.verdict"]
    out: list[Narrative] = []
    now = utcnow().isoformat()

    for lang in languages:
        L = lang
        if L in INTL_LANGUAGES:
            out.extend(build_intl_narratives(
                analysis, decision, roster, L, best=best, actual=actual, alts=alts, res=res, comps=comps,
                refs_core=refs_core,
                analyst_refs=refs_core + [f"results.{keys[c.action_id]}.p_shot" for c in analysis.candidates]
                + ["decision.pressure_count_5m", "decision.nearest_defender_m", "sim.confidence_level"],
                generated_by=generated_by, now=now))
            continue
        best_label = action_label(best, roster, L)
        best_phrase = _phrase(best, roster, L)
        act_noun = _noun(actual, L)
        p_a, p_b = pct(ra.p_goal.value, L), pct(rb.p_goal.value, L)
        verdict = bc.verdict
        notes = _secondary_notes(bc, actual, L)
        # ------------------------------------------------------------------ casual
        if L == "en":
            headline = {"more_promising": "Was there a better option?", "less_promising": "Good call?",
                        "similar": "Different choice, similar chance", "inconclusive": "Too close to call"}[verdict]
            lead = f"In the {_ordinal(minute)} minute, {actor} chose to {_verb(actual, roster, L)} from {dist} m."
            if verdict == "more_promising":
                core = (f"Under our simulation model, {best_phrase} led to a goal within {H} seconds in {p_b} of {n} "
                        f"simulated continuations, against {p_a} for the {act_noun}.")
            elif verdict == "less_promising":
                core = (f"Under our simulation model the {act_noun} was the stronger choice: {p_a} chance of a goal "
                        f"within {H} seconds, against {p_b} for the best alternative, {best_phrase}.")
            elif verdict == "similar":
                core = (f"Under our simulation model the options are close: {p_a} for the {act_noun} and {p_b} for "
                        f"{best_phrase}, over {n} simulated continuations each.")
            else:
                core = (f"Our simulations cannot separate the options with confidence: {p_a} for the {act_noun} and "
                        f"{p_b} for {best_phrase}.")
            extra = f" It also {' and '.join(notes)} than the {act_noun}." if notes else ""
            if actual.action_type == "shoot" and ra.outcome_distribution.get("blocked", 0) >= 0.3:
                extra = f" The shot was blocked in {pct(ra.outcome_distribution['blocked'])} of simulations."
            body = f"{lead} {core}{extra} This is a model estimate, not a record of what would have happened."
        else:
            headline = {"more_promising": "Was er een betere optie?", "less_promising": "Goede keuze?",
                        "similar": "Andere keuze, vergelijkbare kans", "inconclusive": "Te dicht bij elkaar"}[verdict]
            lead = f"In de {minute}e minuut koos {actor} ervoor om vanaf {dist} meter {_verb(actual, roster, L)}."
            if verdict == "more_promising":
                core = (f"Volgens ons simulatiemodel leidde {best_phrase} binnen {H} seconden tot een doelpunt "
                        f"in {p_b} van {n} gesimuleerde vervolgen, tegenover {p_a} voor het {act_noun}.")
            elif verdict == "less_promising":
                core = (f"Volgens ons simulatiemodel was het {act_noun} de sterkere keuze: {p_a} kans op een doelpunt "
                        f"binnen {H} seconden, tegenover {p_b} voor het beste alternatief, {best_phrase}.")
            elif verdict == "similar":
                core = (f"Volgens ons simulatiemodel liggen de opties dicht bij elkaar: {p_a} voor het {act_noun} en "
                        f"{p_b} voor {best_phrase}, elk over {n} gesimuleerde vervolgen.")
            else:
                core = (f"Onze simulaties kunnen de opties niet met zekerheid onderscheiden: {p_a} voor het {act_noun} "
                        f"en {p_b} voor {best_phrase}.")
            extra = f" Bovendien {' en '.join(notes)} dan het {act_noun}." if notes else ""
            if actual.action_type == "shoot" and ra.outcome_distribution.get("blocked", 0) >= 0.3:
                extra = (f" Het schot werd in {pct(ra.outcome_distribution['blocked'], L)} van de simulaties "
                         f"geblokt.")
            body = f"{lead} {core}{extra} Dit is een modelschatting, geen verslag van wat er gebeurd zou zijn."
        out.append(Narrative(
            narrative_id=new_id("nar"), analysis_id=analysis.analysis_id, audience="casual", language=L,
            headline=headline, body=body, evidence_refs=refs_core, generated_by=generated_by,
            is_live_model_output=False, created_at=now))

        # ------------------------------------------------------------------ analyst
        bullets = []
        for c in analysis.candidates:
            r = res[c.action_id]
            lab = action_label(c, roster, L)
            tag = (" (actual)" if L == "en" else " (werkelijk)") if c.is_actual else ""
            if L == "en":
                bullets.append(
                    f"{lab}{tag}: P(goal) {pct(r.p_goal.value)} [{pct(r.p_goal.ci95_low)} to {pct(r.p_goal.ci95_high)}], "
                    f"shot {pct(r.p_shot.value)}, turnover {pct(r.p_turnover.value)}, "
                    f"first action succeeds {pct(r.p_first_action_success.value)}")
            else:
                bullets.append(
                    f"{lab}{tag}: P(doelpunt) {pct(r.p_goal.value, L)} [{pct(r.p_goal.ci95_low, L)} tot "
                    f"{pct(r.p_goal.ci95_high, L)}], schot {pct(r.p_shot.value, L)}, balverlies "
                    f"{pct(r.p_turnover.value, L)}, eerste actie slaagt {pct(r.p_first_action_success.value, L)}")
        for c in alts:
            cm = comps[c.action_id]
            lab = action_label(c, roster, L)
            d, lo, hi = cm.diff_p_goal * 100, cm.diff_ci95_low * 100, cm.diff_ci95_high * 100
            vtxt = {"en": {"more_promising": "more promising", "less_promising": "less promising",
                           "similar": "similar", "inconclusive": "inconclusive"},
                    "nl": {"more_promising": "kansrijker", "less_promising": "minder kansrijk",
                           "similar": "vergelijkbaar", "inconclusive": "niet te onderscheiden"}}[L][cm.verdict]
            if L == "en":
                bullets.append(f"{lab} vs actual: {d:+.1f} pp [{lo:+.1f}, {hi:+.1f}], {vtxt} (paired comparison)")
            else:
                bullets.append(f"{lab} vs werkelijk: {num(d, L):s} pp [{num(lo, L)}, {num(hi, L)}], {vtxt} "
                               f"(gepaarde vergelijking)".replace(" -", " -"))
        f = decision.features
        if L == "en":
            bullets.append(f"Context: {f.pressure_count_5m} opponents within 5 m, nearest defender "
                           f"{num(f.nearest_defender_m)} m, {num(f.distance_to_goal_m)} m from goal.")
            method = (f"All options start from the same frozen snapshot and use {n} paired rollouts each (common random "
                      f"numbers) over a {H} s horizon. Metric: modeled P(goal within {H} s). Intervals are 95% Wilson "
                      f"intervals for simulation error only.")
            head = f"{minute}' {roster[decision.actor_id].name}: {action_label(actual, roster, L)} vs {len(alts)} alternatives"
            vline = {"more_promising": f"{best_label} estimated more promising under the model.",
                     "less_promising": "The observed choice estimated stronger than every alternative under the model.",
                     "similar": "Estimated values are similar under the model.",
                     "inconclusive": "Insufficient evidence to rank these options confidently."}[verdict]
        else:
            bullets.append(f"Context: {f.pressure_count_5m} tegenstanders binnen 5 m, dichtstbijzijnde verdediger op "
                           f"{num(f.nearest_defender_m, L)} m, {num(f.distance_to_goal_m, L)} m van het doel.")
            method = (f"Alle opties starten vanuit dezelfde bevroren momentopname met elk {n} gepaarde simulaties "
                      f"(common random numbers) over {H} s. Maatstaf: gemodelleerde kans op een doelpunt binnen {H} s. "
                      f"Intervallen zijn 95% Wilson-intervallen voor alleen de simulatiefout.")
            head = f"{minute}' {roster[decision.actor_id].name}: {action_label(actual, roster, L)} vs {len(alts)} alternatieven"
            vline = {"more_promising": f"'{best_label}' volgens het model kansrijker.",
                     "less_promising": "De gekozen actie is volgens het model sterker dan elk alternatief.",
                     "similar": "Volgens het model vergelijkbare waarde.",
                     "inconclusive": "Onvoldoende bewijs om deze opties betrouwbaar te rangschikken."}[verdict]
        out.append(Narrative(
            narrative_id=new_id("nar"), analysis_id=analysis.analysis_id, audience="analyst", language=L,
            headline=head, body=f"{vline} {method}", bullets=bullets + ASSUMPTIONS[L],
            evidence_refs=refs_core + [f"results.{keys[c.action_id]}.p_shot" for c in analysis.candidates]
            + ["decision.pressure_count_5m", "decision.nearest_defender_m", "sim.confidence_level"],
            generated_by=generated_by, is_live_model_output=False, created_at=now))

        # ------------------------------------------------------------------ broadcaster
        tgt = roster[best.target_player_id].short_name if best.target_player_id else None
        if L == "en":
            short = f"pass to {tgt}" if best.action_type == "pass" and tgt else best_label.lower()
            caption = {
                "more_promising": f"Model: {short} {p_b} vs {p_a} for the {act_noun} ({n} sims)",
                "less_promising": f"Model backs the {act_noun}: {p_a} vs {p_b} best alternative ({n} sims)",
                "similar": f"Model: {act_noun} {p_a}, {short} {p_b}: too close to separate",
                "inconclusive": f"Model: {act_noun} {p_a}, {short} {p_b}: inconclusive",
            }[verdict]
            b_head = {"more_promising": "THE OTHER OPTION", "less_promising": "RIGHT CALL",
                      "similar": "SAME VALUE, DIFFERENT PATH", "inconclusive": "TOO CLOSE TO CALL"}[verdict]
            b_body = f"Goal chance within {H} s, simulation model, {n} runs per option."
        else:
            short = f"pass naar {tgt}" if best.action_type == "pass" and tgt else best_label.lower()
            caption = {
                "more_promising": f"Model: {short} {p_b} tegen {p_a} voor het {act_noun} ({n} sims)",
                "less_promising": f"Model steunt het {act_noun}: {p_a} tegen {p_b} beste alternatief ({n} sims)",
                "similar": f"Model: {act_noun} {p_a}, {short} {p_b}: te dicht bij elkaar",
                "inconclusive": f"Model: {act_noun} {p_a}, {short} {p_b}: niet te onderscheiden",
            }[verdict]
            b_head = {"more_promising": "DE ANDERE OPTIE", "less_promising": "JUISTE KEUZE",
                      "similar": "ZELFDE WAARDE, ANDER PAD", "inconclusive": "TE DICHT BIJ ELKAAR"}[verdict]
            b_body = f"Kans op een doelpunt binnen {H} s, simulatiemodel, {n} runs per optie."
        out.append(Narrative(
            narrative_id=new_id("nar"), analysis_id=analysis.analysis_id, audience="broadcaster", language=L,
            headline=b_head, body=b_body, caption=caption, evidence_refs=refs_core, generated_by=generated_by,
            is_live_model_output=False, created_at=now))
    _ = cand
    return out

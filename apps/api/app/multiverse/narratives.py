"""Evidence and narratives for adversarial planning (EN/NL, three viewer modes).

Every number in these templates comes from the evidence table and is checked by the same
narrative verifier used for single-decision analyses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.common import new_id, utcnow
from ..models.narrative import Narrative
from ..models.verification import EvidenceItem
from ..simulation.defense import BASELINE
from ..verification.evidence import pct

if TYPE_CHECKING:
    from .workflow import MvContext

OUTCOME_EN = {
    "completed": "the pass reached its target", "loose_won": "the pass ran loose but a teammate won it",
    "intercepted": "the ball was intercepted", "loose_lost": "the ball ran loose and the defence won it",
    "out_of_play": "the ball went out of play", "success": "the dribble got through",
    "interrupted": "the carrier was held up but kept the ball", "tackled": "the dribble was stopped by a tackle",
    "goal": "the shot went in", "saved": "the goalkeeper saved the shot", "blocked": "the shot was blocked",
    "off_target": "the shot missed the target",
}
OUTCOME_NL = {
    "completed": "de pass kwam aan", "loose_won": "de pass sprong los maar een teamgenoot won de bal",
    "intercepted": "de bal werd onderschept", "loose_lost": "de bal sprong los en de verdediging won hem",
    "out_of_play": "de bal ging uit", "success": "de dribbel lukte", "interrupted": "de balbezitter werd opgehouden maar hield de bal",
    "tackled": "de dribbel werd afgestopt met een tackle", "goal": "het schot ging erin", "saved": "de keeper redde het schot",
    "blocked": "het schot werd geblokt", "off_target": "het schot ging naast",
}


def _keys(ctx: MvContext) -> tuple[dict[str, str], dict[str, str]]:
    akeys = {aid: f"a{i + 1}" for i, aid in enumerate(ctx.attack_set)}
    skeys = {sid: ("d0" if sid == BASELINE.strategy_id else f"d{i + 1}")
             for i, sid in enumerate([s for s in ctx.all_strategy_ids() if s != BASELINE.strategy_id])}
    skeys[BASELINE.strategy_id] = "d0"
    return akeys, skeys


def build_multiverse_evidence(ctx: MvContext) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []

    def add(ref: str, label: str, value, unit: str = "", display: str | None = None) -> None:
        if display is None:
            display = pct(float(value)) if unit == "%" else f"{value}{(' ' + unit) if unit else ''}"
        items.append(EvidenceItem(ref=ref, label=label, value=value, unit=unit, display=display))

    p = ctx.planning
    s = p.summary
    akeys, skeys = _keys(ctx)
    add("mv.minute", "Match minute", ctx.node.match_clock_ms // 60000 + 1, "", f"{ctx.node.match_clock_ms // 60000 + 1}'")
    add("mv.rounds", "Planning rounds", len(p.rounds))
    add("mv.rollouts", "Simulations per cell", p.rollouts_per_cell)
    add("mv.horizon_s", "Horizon", int(ctx.horizon_s), "s")
    add("mv.options", "Attacking options", len(ctx.attack_set))
    add("mv.responses", "Defensive responses incl. balanced", len(ctx.all_strategy_ids()))
    add("sim.confidence_level", "Confidence level", 0.95, "%", "95%")
    for aid, ak in akeys.items():
        add(f"actions.{ak}.label", "Attacking option", ctx.action(aid).label)
        for sid, sk in skeys.items():
            if (aid, sid) in ctx.cells:
                c = ctx.cells[(aid, sid)].cell
                add(f"matrix.{ak}.{sk}.xg", f"{ctx.action(aid).label} vs {ctx.strategies.get(sid, BASELINE).label}",
                    c.xg, "%")
                add(f"matrix.{ak}.{sk}.p_turnover", "Turnover probability", c.p_turnover.value, "%")
        if s and aid in s.per_action:
            for k in ("worst", "mean", "best"):
                add(f"actions.{ak}.{k}", f"{k} case expected goals", s.per_action[aid][k], "%")
    for sid, sk in skeys.items():
        add(f"strategies.{sk}.label", "Defensive response", ctx.strategies.get(sid, BASELINE).label)
    if s:
        add("summary.selected_vs_counter", "Selected action vs best counter", s.selected_value_vs_counter, "%")
        add("summary.selected_vs_baseline", "Selected action vs balanced defence", s.selected_value_vs_baseline, "%")
        add("summary.counter_effect_pp", "Counter effect (points)", round(s.counter_effect_pp, 1), "pp",
            f"{s.counter_effect_pp:+.1f} pp")
    if ctx.outcome:
        t = ctx.outcome.transition
        add("transition.first_outcome", "First action outcome in the shown continuation", t.first_outcome)
        add("transition.duration_s", "Duration of the shown continuation", round(t.duration_ms / 1000, 1), "s")
        add("transition.rollout", "Rollout index replayed", t.rollout_index)
    return items


def build_multiverse_narratives(ctx: MvContext) -> list[Narrative]:
    p = ctx.planning
    s = p.summary
    if s is None:
        return []
    roster = ctx.roster
    carrier = roster[ctx.snapshot.ball.possessor_id].short_name if ctx.snapshot.ball.possessor_id else "The carrier"
    sel = ctx.action(s.selected_action_id)
    counter = ctx.strategies.get(s.defensive_counter_id, BASELINE)
    robust = ctx.action(s.most_robust_action_id) if s.most_robust_action_id else sel
    upside = ctx.action(s.highest_upside_action_id) if s.highest_upside_action_id else sel
    H = int(ctx.horizon_s)
    n = p.rollouts_per_cell
    minute = ctx.node.match_clock_ms // 60000 + 1
    revisions = [ap for ap in p.attack_proposals if ap.round > 1 and ap.source == "attacking_agent"]
    first = ctx.outcome.transition.first_outcome if ctx.outcome else None
    now = utcnow().isoformat()
    refs = ["summary.selected_vs_counter", "summary.selected_vs_baseline", "mv.rollouts", "mv.horizon_s", "mv.rounds"]
    out: list[Narrative] = []
    for lang in ctx.languages:
        en = lang == "en"
        sel_label = sel.label.replace(" (actual)", "")
        vc, vb = pct(s.selected_value_vs_counter, lang), pct(s.selected_value_vs_baseline, lang)
        if en:
            weaker = s.selected_value_vs_counter < s.selected_value_vs_baseline
            effect = (f"which lowered the modelled expected goals within {H} seconds from {vb} to {vc}" if weaker else
                      f"but under our simulation model it did not lower the expected goals within {H} seconds ({vc})")
            body = (f"{carrier}: {sel_label}. The defending agent's best answer was '{counter.label}', {effect}. ")
            if revisions:
                body += (f"After seeing the response matrix, the attacking agent changed its plan and added "
                         f"{revisions[-1].action.label}. ")
            if first:
                body += f"In the continuation shown, {OUTCOME_EN.get(first, first)}. "
            body += "This is one modelled future under our simulation model, not what would have happened."
            casual = Narrative(narrative_id=new_id("nar"), analysis_id=p.planning_id, audience="casual", language=lang,
                               headline="Attack vs defence", body=body, evidence_refs=refs, generated_by="policy-template",
                               is_live_model_output=False, created_at=now)
            bullets = []
            akeys, _ = _keys(ctx)
            for aid in ctx.attack_set:
                v = s.per_action[aid]
                bullets.append(f"{ctx.action(aid).label}: worst {pct(v['worst'])}, mean {pct(v['mean'])}, "
                               f"best {pct(v['best'])}")
            bullets.append(f"Most robust against the defensive responses: {robust.label}; highest upside: {upside.label}.")
            bullets.append(f"Counter effect on the selected action: {s.counter_effect_pp:+.1f} pp.")
            bullets.append("Uncertainty: 95% intervals per cell cover Monte Carlo sampling only; the football model is a "
                           "simplified, uncalibrated synthetic model; the frozen state omits body orientation, fatigue "
                           "and communication.")
            analyst = Narrative(
                narrative_id=new_id("nar"), analysis_id=p.planning_id, audience="analyst", language=lang,
                headline=f"{minute}' adversarial plan: {len(ctx.attack_set)} options x {len(ctx.all_strategy_ids())} "
                         f"defensive responses, {len(p.rounds)} round(s)",
                body=(f"Every option was simulated against every defensive response from the same frozen snapshot with "
                      f"{n} paired rollouts per cell over {H} s. Value: modelled expected goals within the horizon "
                      f"(each simulated shot scored by its conditional goal probability)."),
                bullets=bullets, evidence_refs=refs + [f"actions.{k}.worst" for k in akeys.values()],
                generated_by="policy-template", is_live_model_output=False, created_at=now)
            caption = f"Model: {sel_label} {vc} vs best defence ({counter.label})"
            bc = Narrative(narrative_id=new_id("nar"), analysis_id=p.planning_id, audience="broadcaster", language=lang,
                           headline="ATTACK VS DEFENCE", body=f"Expected goals within {H} s, simulation model.",
                           caption=caption[:118], evidence_refs=refs, generated_by="policy-template",
                           is_live_model_output=False, created_at=now)
        else:
            weaker = s.selected_value_vs_counter < s.selected_value_vs_baseline
            effect = (f"waardoor de gemodelleerde verwachte doelpunten binnen {H} seconden daalden van {vb} naar {vc}"
                      if weaker else f"maar volgens ons simulatiemodel daalden de verwachte doelpunten binnen {H} "
                                     f"seconden niet ({vc})")
            body = f"{carrier}: {sel_label}. Het beste antwoord van de verdedigende agent was '{counter.label}', {effect}. "
            if revisions:
                body += (f"Na de responsmatrix paste de aanvallende agent het plan aan en voegde "
                         f"{revisions[-1].action.label} toe. ")
            if first:
                body += f"In het getoonde vervolg {OUTCOME_NL.get(first, first)}. "
            body += "Dit is een gemodelleerde toekomst volgens ons simulatiemodel, niet wat er gebeurd zou zijn."
            casual = Narrative(narrative_id=new_id("nar"), analysis_id=p.planning_id, audience="casual", language=lang,
                               headline="Aanval tegen verdediging", body=body, evidence_refs=refs,
                               generated_by="policy-template", is_live_model_output=False, created_at=now)
            bullets = []
            for aid in ctx.attack_set:
                v = s.per_action[aid]
                bullets.append(f"{ctx.action(aid).label}: slechtst {pct(v['worst'], lang)}, gemiddeld "
                               f"{pct(v['mean'], lang)}, best {pct(v['best'], lang)}")
            bullets.append(f"Meest robuust tegen de verdedigende antwoorden: {robust.label}; grootste potentie: {upside.label}.")
            bullets.append(f"Effect van het tegenantwoord op de gekozen actie: {s.counter_effect_pp:+.1f} pp".replace(".", ",")
                           + ".")
            bullets.append("Onzekerheid: 95%-intervallen per cel dekken alleen de steekproeffout; het voetbalmodel is "
                           "vereenvoudigd en ongekalibreerd; de bevroren toestand mist lichaamshouding, vermoeidheid en "
                           "communicatie.")
            analyst = Narrative(
                narrative_id=new_id("nar"), analysis_id=p.planning_id, audience="analyst", language=lang,
                headline=f"{minute}' tegenspel-plan: {len(ctx.attack_set)} opties x {len(ctx.all_strategy_ids())} "
                         f"verdedigende antwoorden, {len(p.rounds)} ronde(s)",
                body=(f"Elke optie is tegen elk verdedigend antwoord gesimuleerd vanuit dezelfde bevroren momentopname, "
                      f"met {n} gepaarde simulaties per cel over {H} s. Waarde: gemodelleerde verwachte doelpunten binnen "
                      f"de horizon."),
                bullets=bullets, evidence_refs=refs, generated_by="policy-template", is_live_model_output=False,
                created_at=now)
            caption = f"Model: {sel_label} {vc} tegen beste verdediging ({counter.label})"
            bc = Narrative(narrative_id=new_id("nar"), analysis_id=p.planning_id, audience="broadcaster", language=lang,
                           headline="AANVAL TEGEN VERDEDIGING", body=f"Verwachte doelpunten binnen {H} s, simulatiemodel.",
                           caption=caption[:118], evidence_refs=refs, generated_by="policy-template",
                           is_live_model_output=False, created_at=now)
        out += [casual, analyst, bc]
    return out

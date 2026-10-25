"""Deterministic narrative templates for Spanish, French and German.

Same structure and the same evidence-backed numbers as the English and Dutch templates in
`templates.py`; only the wording differs. Like those, every number comes from the evidence table,
so these narratives pass the same verification.
"""

from __future__ import annotations

from ..models.analysis import CounterfactualAnalysis
from ..models.common import new_id
from ..models.decisions import CandidateAction, DecisionPoint
from ..models.match import Player
from ..models.narrative import Narrative
from ..models.simulation import ActionResult, PairwiseComparison
from ..verification.evidence import num, pct

INTL_LANGUAGES = ("es", "fr", "de")

ASSUMPTIONS = {
    "es": [
        "Partido sintético y física simplificada: los jugadores se mueven en línea recta a velocidad limitada tras un tiempo de reacción.",
        "No se modelan rechaces ni jugadas a balón parado; un tiro parado o bloqueado termina la simulación.",
        "El fuera de juego se aproxima como un límite a los desmarques, no se arbitra.",
        "Los intervalos solo recogen el error de muestreo Monte Carlo, no el error del modelo. No está calibrado con partidos reales.",
    ],
    "fr": [
        "Match synthétique et physique simplifiée : après un temps de réaction, les joueurs se déplacent en ligne droite à vitesse limitée.",
        "Les rebonds et les coups de pied arrêtés ne sont pas modélisés ; un tir arrêté ou contré termine la simulation.",
        "Le hors-jeu est approché comme une limite sur les appels, il n'est pas arbitré.",
        "Les intervalles ne couvrent que l'erreur d'échantillonnage Monte-Carlo, pas l'erreur du modèle. Non calibré sur de vrais matchs.",
    ],
    "de": [
        "Synthetisches Spiel und vereinfachte Physik: Spieler bewegen sich nach einer Reaktionszeit geradlinig mit begrenztem Tempo.",
        "Abpraller und Standardsituationen werden nicht modelliert; ein gehaltener oder geblockter Schuss beendet die Simulation.",
        "Abseits wird als Grenze für Laufwege angenähert, nicht entschieden.",
        "Die Intervalle erfassen nur den Monte-Carlo-Stichprobenfehler, nicht den Modellfehler. Nicht an echten Spielen kalibriert.",
    ],
}

_DRIBBLES = {
    "es": {"Dribble towards goal": "Regate hacia la portería", "Dribble diagonally right": "Regate en diagonal a la derecha",
           "Dribble diagonally left": "Regate en diagonal a la izquierda", "Dribble wide right": "Regate por la banda derecha",
           "Dribble wide left": "Regate por la banda izquierda"},
    "fr": {"Dribble towards goal": "Dribble vers le but", "Dribble diagonally right": "Dribble en diagonale à droite",
           "Dribble diagonally left": "Dribble en diagonale à gauche", "Dribble wide right": "Dribble côté droit",
           "Dribble wide left": "Dribble côté gauche"},
    "de": {"Dribble towards goal": "Dribbling Richtung Tor", "Dribble diagonally right": "Dribbling diagonal nach rechts",
           "Dribble diagonally left": "Dribbling diagonal nach links", "Dribble wide right": "Dribbling über rechts",
           "Dribble wide left": "Dribbling über links"},
}
_DRIBBLE_DEFAULT = {"es": "Regate", "fr": "Dribble", "de": "Dribbling"}

# Grammatical forms of the observed action: (subject form, form after "for"/"than").
_NOUN = {
    "es": {"shoot": ("el tiro", "el tiro"), "pass": ("el pase", "el pase"), "dribble": ("el regate", "el regate")},
    "fr": {"shoot": ("le tir", "le tir"), "pass": ("la passe", "la passe"), "dribble": ("le dribble", "le dribble")},
    "de": {"shoot": ("der Schuss", "den Schuss"), "pass": ("der Pass", "den Pass"), "dribble": ("das Dribbling", "das Dribbling")},
}
_BARE = {"es": {"shoot": "tiro", "pass": "pase", "dribble": "regate"},
         "fr": {"shoot": "tir", "pass": "passe", "dribble": "dribble"},
         "de": {"shoot": "Schuss", "pass": "Pass", "dribble": "Dribbling"}}

_VERDICT = {
    "es": {"more_promising": "más prometedora", "less_promising": "menos prometedora", "similar": "similar",
           "inconclusive": "no concluyente"},
    "fr": {"more_promising": "plus prometteuse", "less_promising": "moins prometteuse", "similar": "similaire",
           "inconclusive": "non concluante"},
    "de": {"more_promising": "vielversprechender", "less_promising": "weniger vielversprechend", "similar": "ähnlich",
           "inconclusive": "nicht eindeutig"},
}


def action_label(c: CandidateAction, roster: dict[str, Player], lang: str) -> str:
    t = roster[c.target_player_id].short_name if c.target_player_id else None
    base = c.label.replace(" (actual)", "")
    through = base.startswith("Through")
    if c.action_type == "shoot":
        return {"es": "Tiro", "fr": "Tir", "de": "Schuss"}[lang]
    if c.action_type == "pass" and t:
        if lang == "es":
            return f"Pase al hueco a {t}" if through else f"Pase a {t}"
        if lang == "fr":
            return f"Passe en profondeur à {t}" if through else f"Passe à {t}"
        return f"Steilpass zu {t}" if through else f"Pass zu {t}"
    return _DRIBBLES[lang].get(base, _DRIBBLE_DEFAULT[lang])


def _phrase(c: CandidateAction, roster: dict[str, Player], lang: str, after_for: bool = False) -> str:
    """'un pase a X' / 'une passe à X' / 'ein Pass zu X' (German accusative after 'für')."""
    lab = action_label(c, roster, lang)
    if lang == "es":
        return "un " + lab[0].lower() + lab[1:]
    if lang == "fr":
        art = "une" if c.action_type == "pass" else "un"
        return f"{art} {lab[0].lower()}{lab[1:]}"
    if c.action_type == "dribble":
        return f"ein {lab}"
    return f"{'einen' if after_for else 'ein'} {lab}"


def _verb(c: CandidateAction, roster: dict[str, Player], lang: str) -> str:
    t = roster[c.target_player_id].short_name if c.target_player_id else None
    return {
        "es": {"shoot": "disparar", "pass": f"pasar a {t}", "dribble": "regatear"},
        "fr": {"shoot": "de tirer", "pass": f"de passer à {t}", "dribble": "de dribbler"},
        "de": {"shoot": "zu schießen", "pass": f"zu {t} zu passen", "dribble": "zu dribbeln"},
    }[lang][c.action_type]


def _notes(cm: PairwiseComparison, actual: CandidateAction, lang: str) -> list[str]:
    words = {
        "es": ("genera un tiro más a menudo", "genera un tiro con menos frecuencia", "pierde el balón más a menudo",
               "pierde el balón con menos frecuencia"),
        "fr": ("mène plus souvent à un tir", "mène moins souvent à un tir", "perd plus souvent le ballon",
               "perd moins souvent le ballon"),
        "de": ("führt häufiger zu einem Schuss", "führt seltener zu einem Schuss", "verliert häufiger den Ball",
               "verliert seltener den Ball"),
    }[lang]
    if actual.action_type == "shoot":
        return []
    notes: list[str] = []
    if cm.diff_p_shot_ci95_low > 0:
        notes.append(words[0])
    elif cm.diff_p_shot_ci95_high < 0:
        notes.append(words[1])
    if cm.diff_p_turnover_ci95_low > 0:
        notes.append(words[2])
    elif cm.diff_p_turnover_ci95_high < 0:
        notes.append(words[3])
    return notes


def _signed(v: float, lang: str) -> str:
    return f"{v:+.1f}".replace(".", ",")


def build_intl_narratives(analysis: CounterfactualAnalysis, decision: DecisionPoint, roster: dict[str, Player],
                          lang: str, *, best: CandidateAction, actual: CandidateAction, alts: list[CandidateAction],
                          res: dict[str, ActionResult], comps: dict[str, PairwiseComparison],
                          refs_core: list[str], analyst_refs: list[str], generated_by: str, now: str) -> list[Narrative]:
    sim = analysis.simulation
    assert sim is not None
    n, H = sim.config.rollouts, int(sim.config.horizon_s)
    minute = decision.match_clock_ms // 60000 + 1
    actor = roster[decision.actor_id].short_name
    dist = round(decision.features.distance_to_goal_m)
    ra, rb, bc = res[actual.action_id], res[best.action_id], comps[best.action_id]
    p_a, p_b = pct(ra.p_goal.value, lang), pct(rb.p_goal.value, lang)
    verdict = bc.verdict
    subj, obj = _NOUN[lang][actual.action_type]
    bare = _BARE[lang][actual.action_type]
    best_label = action_label(best, roster, lang)
    bp, bp_for = _phrase(best, roster, lang), _phrase(best, roster, lang, after_for=True)
    notes = _notes(bc, actual, lang)
    blocked = ra.outcome_distribution.get("blocked", 0) if actual.action_type == "shoot" else 0
    blocked_pct = pct(blocked, lang)
    out: list[Narrative] = []

    def add(audience: str, headline: str, body: str, bullets: list[str] | None = None, caption: str | None = None,
            refs: list[str] | None = None) -> None:
        out.append(Narrative(narrative_id=new_id("nar"), analysis_id=analysis.analysis_id, audience=audience,
                             language=lang, headline=headline, body=body, bullets=bullets or [], caption=caption,
                             evidence_refs=refs or refs_core, generated_by=generated_by, is_live_model_output=False,
                             created_at=now))

    # ------------------------------------------------------------------ casual
    if lang == "es":
        headline = {"more_promising": "¿Había una opción mejor?", "less_promising": "¿Buena decisión?",
                    "similar": "Otra elección, una probabilidad parecida", "inconclusive": "Demasiado igualado"}[verdict]
        lead = f"En el minuto {minute}, {actor} decidió {_verb(actual, roster, lang)} desde {dist} m."
        core = {
            "more_promising": f"Según nuestro modelo de simulación, {bp} acabó en gol en {H} segundos en el {p_b} de "
                              f"{n} continuaciones simuladas, frente al {p_a} del {bare}.",
            "less_promising": f"Según nuestro modelo de simulación, {subj} fue la mejor elección: {p_a} de probabilidad "
                              f"de gol en {H} segundos, frente al {p_b} de la mejor alternativa, {bp}.",
            "similar": f"Según nuestro modelo de simulación, las opciones están muy igualadas: {p_a} para {obj} y {p_b} "
                       f"para {bp}, con {n} continuaciones simuladas cada una.",
            "inconclusive": f"Nuestras simulaciones no pueden separar las opciones con confianza: {p_a} para {obj} y "
                            f"{p_b} para {bp}.",
        }[verdict]
        extra = f" Además, esta opción {' y '.join(notes)} que {obj}." if notes else ""
        if blocked >= 0.3:
            extra = f" El tiro fue bloqueado en el {blocked_pct} de las simulaciones."
        close = " Es una estimación del modelo, no un registro de lo que habría pasado."
    elif lang == "fr":
        headline = {"more_promising": "Y avait-il une meilleure option ?", "less_promising": "Bon choix ?",
                    "similar": "Autre choix, chance similaire", "inconclusive": "Trop serré pour trancher"}[verdict]
        lead = f"À la {minute}e minute, {actor} a choisi {_verb(actual, roster, lang)} à {dist} m."
        core = {
            "more_promising": f"Selon notre modèle de simulation, {bp} a mené à un but en moins de {H} secondes dans "
                              f"{p_b} des {n} suites simulées, contre {p_a} pour {obj}.",
            "less_promising": f"Selon notre modèle de simulation, {subj} était le meilleur choix : {p_a} de chances de "
                              f"but en {H} secondes, contre {p_b} pour la meilleure alternative, {bp}.",
            "similar": f"Selon notre modèle de simulation, les options sont proches : {p_a} pour {obj} et {p_b} pour "
                       f"{bp}, sur {n} suites simulées chacune.",
            "inconclusive": f"Nos simulations ne permettent pas de départager les options avec confiance : {p_a} pour "
                            f"{obj} et {p_b} pour {bp}.",
        }[verdict]
        extra = f" De plus, cette option {' et '.join(notes)} que {obj}." if notes else ""
        if blocked >= 0.3:
            extra = f" Le tir a été contré dans {blocked_pct} des simulations."
        close = " C'est une estimation du modèle, pas le récit de ce qui se serait passé."
    else:
        headline = {"more_promising": "Gab es eine bessere Option?", "less_promising": "Richtige Entscheidung?",
                    "similar": "Andere Wahl, ähnliche Chance", "inconclusive": "Zu knapp für ein Urteil"}[verdict]
        lead = f"In der {minute}. Minute entschied sich {actor}, aus {dist} m {_verb(actual, roster, lang)}."
        core = {
            "more_promising": f"Laut unserem Simulationsmodell führte {bp} in {p_b} von {n} simulierten Verläufen "
                              f"innerhalb von {H} Sekunden zu einem Tor, gegenüber {p_a} für {obj}.",
            "less_promising": f"Laut unserem Simulationsmodell war {subj} die stärkere Wahl: {p_a} Torchance innerhalb "
                              f"von {H} Sekunden, gegenüber {p_b} für die beste Alternative, {bp_for}.",
            "similar": f"Laut unserem Simulationsmodell liegen die Optionen eng beieinander: {p_a} für {obj} und {p_b} "
                       f"für {bp_for}, bei je {n} simulierten Verläufen.",
            "inconclusive": f"Unsere Simulationen können die Optionen nicht verlässlich trennen: {p_a} für {obj} und "
                            f"{p_b} für {bp_for}.",
        }[verdict]
        extra = f" Diese Option {' und '.join(notes)} als {subj}." if notes else ""
        if blocked >= 0.3:
            extra = f" Der Schuss wurde in {blocked_pct} der Simulationen geblockt."
        close = " Das ist eine Modellschätzung, kein Bericht darüber, was passiert wäre."
    add("casual", headline, f"{lead} {core}{extra}{close}")

    # ------------------------------------------------------------------ analyst
    W = {
        "es": ("P(gol)", "a", "tiro", "pérdida", "primera acción con éxito", " (real)", "frente a la real",
               "comparación pareada"),
        "fr": ("P(but)", "à", "tir", "perte de balle", "première action réussie", " (réel)", "vs réel",
               "comparaison appariée"),
        "de": ("P(Tor)", "bis", "Schuss", "Ballverlust", "erste Aktion gelingt", " (tatsächlich)", "vs. tatsächlich",
               "gepaarter Vergleich"),
    }[lang]
    bullets = []
    for c in analysis.candidates:
        r = res[c.action_id]
        tag = W[5] if c.is_actual else ""
        bullets.append(f"{action_label(c, roster, lang)}{tag}: {W[0]} {pct(r.p_goal.value, lang)} "
                       f"[{pct(r.p_goal.ci95_low, lang)} {W[1]} {pct(r.p_goal.ci95_high, lang)}], {W[2]} "
                       f"{pct(r.p_shot.value, lang)}, {W[3]} {pct(r.p_turnover.value, lang)}, {W[4]} "
                       f"{pct(r.p_first_action_success.value, lang)}")
    for c in alts:
        cm = comps[c.action_id]
        d, lo, hi = cm.diff_p_goal * 100, cm.diff_ci95_low * 100, cm.diff_ci95_high * 100
        bullets.append(f"{action_label(c, roster, lang)} {W[6]}: {_signed(d, lang)} pp [{_signed(lo, lang)}; "
                       f"{_signed(hi, lang)}], {_VERDICT[lang][cm.verdict]} ({W[7]})")
    f = decision.features
    nd, dg = num(f.nearest_defender_m, lang), num(f.distance_to_goal_m, lang)
    name = roster[decision.actor_id].name
    act_label = action_label(actual, roster, lang)
    if lang == "es":
        bullets.append(f"Contexto: {f.pressure_count_5m} rivales a menos de 5 m, defensor más cercano a {nd} m, a {dg} m "
                       f"de la portería.")
        method = (f"Todas las opciones parten de la misma instantánea congelada y usan {n} simulaciones pareadas cada una "
                  f"(números aleatorios comunes) en un horizonte de {H} s. Métrica: probabilidad modelada de gol en {H} s. "
                  f"Los intervalos son intervalos de Wilson al 95% solo para el error de simulación.")
        head = f"{minute}' {name}: {act_label} frente a {len(alts)} alternativas"
        vline = {"more_promising": f"Según el modelo, «{best_label}» es más prometedora.",
                 "less_promising": "Según el modelo, la elección real es mejor que todas las alternativas.",
                 "similar": "Según el modelo, los valores son similares.",
                 "inconclusive": "No hay pruebas suficientes para ordenar estas opciones con confianza."}[verdict]
    elif lang == "fr":
        bullets.append(f"Contexte : {f.pressure_count_5m} adversaires à moins de 5 m, défenseur le plus proche à {nd} m, "
                       f"à {dg} m du but.")
        method = (f"Toutes les options partent du même instantané figé et utilisent chacune {n} simulations appariées "
                  f"(nombres aléatoires communs) sur un horizon de {H} s. Mesure : probabilité modélisée de but en {H} s. "
                  f"Les intervalles sont des intervalles de Wilson à 95% pour la seule erreur de simulation.")
        head = f"{minute}' {name} : {act_label} vs {len(alts)} alternatives"
        vline = {"more_promising": f"Selon le modèle, « {best_label} » est plus prometteuse.",
                 "less_promising": "Selon le modèle, le choix réel est meilleur que toutes les alternatives.",
                 "similar": "Selon le modèle, les valeurs sont similaires.",
                 "inconclusive": "Pas assez d'éléments pour classer ces options avec confiance."}[verdict]
    else:
        bullets.append(f"Kontext: {f.pressure_count_5m} Gegner im Umkreis von 5 m, nächster Verteidiger {nd} m entfernt, "
                       f"{dg} m vom Tor.")
        method = (f"Alle Optionen starten vom selben eingefrorenen Spielzustand und nutzen je {n} gepaarte Simulationen "
                  f"(gemeinsame Zufallszahlen) über {H} s. Maß: modellierte Torwahrscheinlichkeit innerhalb von {H} s. "
                  f"Die Intervalle sind Wilson-Intervalle (95%) nur für den Simulationsfehler.")
        head = f"{minute}' {name}: {act_label} vs. {len(alts)} Alternativen"
        vline = {"more_promising": f"„{best_label}“ ist laut Modell vielversprechender.",
                 "less_promising": "Die tatsächliche Wahl ist laut Modell stärker als jede Alternative.",
                 "similar": "Laut Modell ähnliche Werte.",
                 "inconclusive": "Nicht genug Belege, um diese Optionen verlässlich zu ordnen."}[verdict]
    add("analyst", head, f"{vline} {method}", bullets + ASSUMPTIONS[lang], refs=analyst_refs)

    # ------------------------------------------------------------------ broadcaster
    tgt = roster[best.target_player_id].short_name if best.target_player_id else None
    if lang == "es":
        short = f"pase a {tgt}" if best.action_type == "pass" and tgt else best_label.lower()
        caption = {"more_promising": f"Modelo: {short} {p_b} frente a {p_a} del {bare} ({n} sims)",
                   "less_promising": f"El modelo respalda {subj}: {p_a} frente a {p_b} de la mejor alternativa ({n} sims)",
                   "similar": f"Modelo: {bare} {p_a}, {short} {p_b}: demasiado igualado",
                   "inconclusive": f"Modelo: {bare} {p_a}, {short} {p_b}: no concluyente"}[verdict]
        b_head = {"more_promising": "LA OTRA OPCIÓN", "less_promising": "DECISIÓN ACERTADA",
                  "similar": "MISMO VALOR, OTRO CAMINO", "inconclusive": "DEMASIADO IGUALADO"}[verdict]
        b_body = f"Probabilidad de gol en {H} s, modelo de simulación, {n} simulaciones por opción."
    elif lang == "fr":
        short = f"passe à {tgt}" if best.action_type == "pass" and tgt else best_label.lower()
        caption = {"more_promising": f"Modèle : {short} {p_b} contre {p_a} pour {obj} ({n} sims)",
                   "less_promising": f"Le modèle valide {obj} : {p_a} contre {p_b} meilleure alternative ({n} sims)",
                   "similar": f"Modèle : {bare} {p_a}, {short} {p_b} : trop serré",
                   "inconclusive": f"Modèle : {bare} {p_a}, {short} {p_b} : non concluant"}[verdict]
        b_head = {"more_promising": "L'AUTRE OPTION", "less_promising": "BON CHOIX",
                  "similar": "MÊME VALEUR, AUTRE CHEMIN", "inconclusive": "TROP SERRÉ"}[verdict]
        b_body = f"Probabilité de but en {H} s, modèle de simulation, {n} simulations par option."
    else:
        short = f"Pass zu {tgt}" if best.action_type == "pass" and tgt else best_label
        caption = {"more_promising": f"Modell: {short} {p_b} vs. {p_a} für {obj} ({n} Sims)",
                   "less_promising": f"Modell stützt {obj}: {p_a} vs. {p_b} beste Alternative ({n} Sims)",
                   "similar": f"Modell: {bare} {p_a}, {short} {p_b}: zu knapp",
                   "inconclusive": f"Modell: {bare} {p_a}, {short} {p_b}: nicht eindeutig"}[verdict]
        b_head = {"more_promising": "DIE ANDERE OPTION", "less_promising": "RICHTIGE WAHL",
                  "similar": "GLEICHER WERT, ANDERER WEG", "inconclusive": "ZU KNAPP"}[verdict]
        b_body = f"Torchance innerhalb von {H} s, Simulationsmodell, {n} Läufe pro Option."
    add("broadcaster", b_head, b_body, caption=caption)
    return out

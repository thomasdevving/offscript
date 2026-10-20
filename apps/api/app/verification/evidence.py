"""Evidence table: every number a narrative may cite, with a stable reference.

Narratives may only state numbers that appear here (within display rounding), so every
user-facing claim is traceable to a computed field.
"""

from __future__ import annotations

from ..models.analysis import CounterfactualAnalysis
from ..models.decisions import DecisionPoint
from ..models.match import Player
from ..models.verification import EvidenceItem


def pct(value: float, language: str = "en", digits: int = 1) -> str:
    s = f"{value * 100:.{digits}f}%"
    return s.replace(".", ",") if language == "nl" else s


def num(value: float, language: str = "en", digits: int = 1) -> str:
    s = f"{value:.{digits}f}"
    return s.replace(".", ",") if language == "nl" else s


def action_keys(analysis: CounterfactualAnalysis) -> dict[str, str]:
    """Readable stable keys: the observed action is `actual`, alternatives are `alt1`, `alt2`..."""
    keys: dict[str, str] = {}
    k = 0
    for c in analysis.candidates:
        if c.is_actual:
            keys[c.action_id] = "actual"
        else:
            k += 1
            keys[c.action_id] = f"alt{k}"
    return keys


def build_evidence(analysis: CounterfactualAnalysis, decision: DecisionPoint, roster: dict[str, Player]
                   ) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []

    def add(ref: str, label: str, value, unit: str = "", display: str | None = None) -> None:
        if value is None:
            return
        if display is None:
            if unit == "%":
                display = pct(float(value))
            elif isinstance(value, float):
                display = f"{value:.1f}{(' ' + unit) if unit else ''}"
            else:
                display = f"{value}{(' ' + unit) if unit else ''}"
        items.append(EvidenceItem(ref=ref, label=label, value=value, unit=unit, display=display))

    minute = decision.match_clock_ms // 60000 + 1
    add("decision.minute", "Match minute", minute, "", f"{minute}'")
    add("decision.actor", "Player on the ball", decision.actor_name)
    f = decision.features
    add("decision.distance_to_goal_m", "Distance to goal", round(f.distance_to_goal_m, 1), "m")
    add("decision.pressure_count_5m", "Opponents within 5 m", f.pressure_count_5m)
    add("decision.pressure_radius_m", "Radius used for the pressure count", 5, "m")
    add("decision.nearest_defender_m", "Nearest defender", round(f.nearest_defender_m, 1), "m")
    add("decision.open_teammates", "Teammates with a likely-completed pass (model)", f.open_teammates)
    if f.actual_shot_quality is not None:
        add("decision.actual_shot_quality", "Modeled scoring probability of the shot itself",
            f.actual_shot_quality, "%")
    if f.actual_pass_difficulty is not None:
        add("decision.actual_pass_difficulty", "Modeled pass difficulty", f.actual_pass_difficulty, "%")
    add("decision.observed_outcome", "Observed outcome (synthetic match)", decision.actual_outcome)

    n_alts = sum(1 for c in analysis.candidates if not c.is_actual)
    add("analysis.alternatives", "Alternatives compared with the observed action", n_alts)
    add("analysis.options", "Options compared (including the observed action)", len(analysis.candidates))
    sim = analysis.simulation
    keys = action_keys(analysis)
    if sim is not None:
        add("sim.rollouts", "Simulated continuations per option", sim.config.rollouts)
        add("sim.horizon_s", "Scoring horizon", int(sim.config.horizon_s) if sim.config.horizon_s.is_integer()
            else sim.config.horizon_s, "s")
        add("sim.seed", "Simulation seed", sim.config.seed)
        add("sim.version", "Simulator version", sim.simulator_version)
        cand = {c.action_id: c for c in analysis.candidates}
        for r in sim.results:
            k = keys.get(r.action_id, r.action_id)
            c = cand.get(r.action_id)
            label = c.label if c else r.action_id
            add(f"results.{k}.label", f"{k} label", label)
            add(f"results.{k}.n", f"{label}: simulated continuations", r.n_rollouts)
            add(f"results.{k}.p_goal", f"{label}: P(goal within horizon)", r.p_goal.value, "%")
            add(f"results.{k}.p_goal_ci_low", f"{label}: 95% interval low", r.p_goal.ci95_low, "%")
            add(f"results.{k}.p_goal_ci_high", f"{label}: 95% interval high", r.p_goal.ci95_high, "%")
            add(f"results.{k}.goals", f"{label}: simulated goals", r.p_goal.successes)
            add(f"results.{k}.p_shot", f"{label}: P(shot within horizon)", r.p_shot.value, "%")
            add(f"results.{k}.p_turnover", f"{label}: P(turnover)", r.p_turnover.value, "%")
            add(f"results.{k}.p_blocked", f"{label}: share of rollouts ending in a blocked shot",
                r.outcome_distribution.get("blocked", 0.0), "%")
            add(f"results.{k}.p_saved", f"{label}: share of rollouts ending in a save",
                r.outcome_distribution.get("saved", 0.0), "%")
            add(f"results.{k}.p_first_action_success", f"{label}: first action succeeds", r.p_first_action_success.value,
                "%")
            if r.mean_time_to_shot_s is not None:
                add(f"results.{k}.mean_time_to_shot_s", f"{label}: mean time to shot", round(r.mean_time_to_shot_s, 1),
                    "s")
            for fk, fv in (c.features.items() if c else []):
                if fk in ("pass_length_m", "dribble_length_m", "distance_to_goal_m", "receiver_distance_to_goal_m"):
                    add(f"candidates.{k}.{fk}", f"{label}: {fk.replace('_', ' ')}", round(fv, 1), "m")
            if c and c.target_player_id:
                add(f"candidates.{k}.target", f"{label}: target player", roster[c.target_player_id].name)
        add("sim.confidence_level", "Confidence level of the Monte Carlo intervals", 0.95, "%", "95%")
        for cmp in sim.comparisons:
            k = keys.get(cmp.action_id, cmp.action_id)
            add(f"comparisons.{k}.diff_p_goal", f"{k} minus actual: P(goal) difference (points)",
                round(cmp.diff_p_goal * 100, 1), "pp", f"{cmp.diff_p_goal * 100:+.1f} pp")
            add(f"comparisons.{k}.diff_ci_low", f"{k} minus actual: interval low (points)",
                round(cmp.diff_ci95_low * 100, 1), "pp", f"{cmp.diff_ci95_low * 100:+.1f} pp")
            add(f"comparisons.{k}.diff_ci_high", f"{k} minus actual: interval high (points)",
                round(cmp.diff_ci95_high * 100, 1), "pp", f"{cmp.diff_ci95_high * 100:+.1f} pp")
            add(f"comparisons.{k}.diff_p_turnover", f"{k} minus actual: turnover difference (points)",
                round(cmp.diff_p_turnover * 100, 1), "pp", f"{cmp.diff_p_turnover * 100:+.1f} pp")
            add(f"comparisons.{k}.diff_p_shot", f"{k} minus actual: shot difference (points)",
                round(cmp.diff_p_shot * 100, 1), "pp", f"{cmp.diff_p_shot * 100:+.1f} pp")
            add(f"comparisons.{k}.verdict", f"{k} vs actual verdict", cmp.verdict)
        if sim.overall_verdict:
            add("sim.overall_verdict", "Overall verdict", sim.overall_verdict)
    return items


def evidence_numbers(items: list[EvidenceItem]) -> list[float]:
    """All numeric values a narrative may cite, in the units they would be written in."""
    out: list[float] = []
    for it in items:
        if isinstance(it.value, bool) or not isinstance(it.value, int | float):
            continue
        v = float(it.value)
        out.append(v)
        if it.unit == "%":
            out.append(v * 100)
    return out

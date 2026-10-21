"""Decision Value Added (DVA): a match-level metric built only from verified decision analyses.

Per analysed decision (probabilities, primary metric P(goal within H s)):

    DVA = P(goal | chosen action) - P(goal | best available option under the model)

where the best option is the candidate with the highest estimated P(goal), the chosen action
included. Writing b for the highest-scoring *alternative* and d for the paired mean of
goal(chosen) - goal(b) over the common-random-number rollouts, DVA = min(0, d): zero when
the chosen action was the best option, negative otherwise. Its 95% interval is the paired
interval of d mapped through min(0, .), which is monotone, so it keeps its coverage for
min(0, true d) given b.

Aggregates (per player, per team, whole match) over n decisions:

    sum  = sum of DVA_i,  mean = sum / n
    se_i = (paired_ci95_high_i - paired_ci95_low_i) / (2 * 1.96)   (unclipped paired interval)
    sum interval = sum -/+ 1.96 * sqrt(sum of se_i^2), upper end capped at 0

Decisions are treated as independent (an approximation: different states, but the snapshots of
a synthetic match share its seed, so the random streams are reused), and the unclipped se_i is
used because clipping cannot increase variance. Every interval describes Monte Carlo error only, never whether the model is
right. Below `MIN_DECISIONS` an aggregate is reported as "not enough decisions" (no numbers).
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from ..models.analysis import CounterfactualAnalysis
from ..models.common import utcnow
from ..models.decision_value import (
    DecisionValueAggregate,
    DecisionValueItem,
    DecisionValueReport,
    DecisionValueScope,
)
from ..models.decisions import DecisionPoint
from .store import MatchData

Z95 = 1.96
MIN_DECISIONS = 3

METHOD = (
    "Decision Value Added (DVA) per decision = P(goal within the horizon | chosen action) - P(goal | best option "
    "under the model), estimated from the verified analysis' paired Monte Carlo rollouts: min(0, paired mean of "
    "goal(chosen) - goal(best alternative)), with that paired 95% interval mapped through min(0, .). 0 means the "
    "chosen action was the model's best option; negative values are modelled goal chance left on the table. Player, "
    "team and match totals sum the per-decision values; their 95% interval combines the paired standard errors in "
    "quadrature (decisions treated as independent; capped at 0). Only verified analyses of detected decisions count; "
    f"fewer than {MIN_DECISIONS} decisions is reported as not enough decisions."
)

DISCLAIMER = (
    "Synthetic match with fictional players. DVA is a model estimate: it inherits every assumption of OFFSCRIPT's "
    "uncalibrated simulator and candidate generator, and its intervals cover Monte Carlo error only."
)


def _r(x: float) -> float:
    return round(x, 6) + 0.0  # no "-0.0" in the JSON


def decision_value(analysis: CounterfactualAnalysis, decision: DecisionPoint) -> DecisionValueItem | None:
    """DVA of one verified analysis; None when it cannot be computed (not verified, no simulated alternative)."""
    sim = analysis.simulation
    if analysis.status != "verified" or sim is None or not sim.comparisons:
        return None
    chosen_id = analysis.actual_action_id or next((c.action_id for c in analysis.candidates if c.is_actual), None)
    results = {r.action_id: r for r in sim.results}
    comps = [c for c in sim.comparisons if c.baseline_action_id == chosen_id and c.action_id in results]
    if chosen_id not in results or not comps:
        return None
    labels = {c.action_id: c.label or c.action_id for c in analysis.candidates}
    # Highest-scoring alternative (first in candidate order on ties, so the result is deterministic).
    order = {c.action_id: i for i, c in enumerate(analysis.candidates)}
    best_alt = max(comps, key=lambda c: (c.diff_p_goal, -order.get(c.action_id, 0)))
    d, lo, hi = -best_alt.diff_p_goal, -best_alt.diff_ci95_high, -best_alt.diff_ci95_low
    best_id = best_alt.action_id if d < 0 else chosen_id
    chosen = results[chosen_id]
    return DecisionValueItem(
        decision_point_id=decision.decision_point_id, analysis_id=analysis.analysis_id,
        match_clock_ms=decision.match_clock_ms, player_id=decision.actor_id, player_name=decision.actor_name,
        team_id=decision.team_id, chosen_action_id=chosen_id, chosen_label=labels.get(chosen_id, chosen_id),
        chosen_p_goal=chosen.p_goal.value, best_action_id=best_id, best_label=labels.get(best_id, best_id),
        best_p_goal=results[best_id].p_goal.value, best_alternative_action_id=best_alt.action_id,
        paired_diff=_r(d), paired_ci95_low=_r(lo), paired_ci95_high=_r(hi),
        dva=_r(min(0.0, d)), ci95_low=_r(min(0.0, lo)), ci95_high=_r(min(0.0, hi)),
        clearly_better_alternative=hi < 0, alternatives=len(comps), n_rollouts=chosen.n_rollouts)


def aggregate(items: Iterable[DecisionValueItem], scope: DecisionValueScope, key: str, name: str,
              team_id: str | None = None, min_decisions: int = MIN_DECISIONS) -> DecisionValueAggregate:
    """Sum and mean DVA with a combined 95% interval; numbers withheld below `min_decisions`."""
    items = list(items)
    n = len(items)
    agg = DecisionValueAggregate(scope=scope, key=key, name=name, team_id=team_id, n_decisions=n,
                                 enough_decisions=n >= max(1, min_decisions),
                                 clear_misses=sum(1 for i in items if i.clearly_better_alternative))
    if not agg.enough_decisions:
        return agg
    total = sum(i.dva for i in items)
    se = math.sqrt(sum(((i.paired_ci95_high - i.paired_ci95_low) / (2 * Z95)) ** 2 for i in items))
    lo, hi = total - Z95 * se, min(0.0, total + Z95 * se)
    agg.dva_sum, agg.dva_sum_ci95_low, agg.dva_sum_ci95_high = _r(total), _r(lo), _r(hi)
    agg.dva_mean, agg.dva_mean_ci95_low, agg.dva_mean_ci95_high = _r(total / n), _r(lo / n), _r(hi / n)
    return agg


def latest_verified(analyses: Iterable[CounterfactualAnalysis], decision_ids: set[str]
                    ) -> dict[str, CounterfactualAnalysis]:
    """One verified, fault-free analysis per decision: most rollouts first, then the most recent."""
    best: dict[str, CounterfactualAnalysis] = {}

    def rank(a: CounterfactualAnalysis) -> tuple[int, str]:
        n = a.simulation.results[0].n_rollouts if a.simulation and a.simulation.results else 0
        return n, a.completed_at or a.created_at

    for a in analyses:
        if a.status != "verified" or a.fault_injection or a.decision_point_id not in decision_ids:
            continue
        cur = best.get(a.decision_point_id)
        if cur is None or rank(a) > rank(cur):
            best[a.decision_point_id] = a
    return best


def _sort_key(a: DecisionValueAggregate) -> tuple:
    return (not a.enough_decisions, a.dva_sum if a.dva_sum is not None else 0.0, -a.n_decisions, a.name)


def build_report(md: MatchData, analyses: Iterable[CounterfactualAnalysis], pending_ids: Iterable[str] = (),
                 min_decisions: int = MIN_DECISIONS) -> DecisionValueReport:
    """DVA report for a match from whatever verified analyses exist (detected decisions only)."""
    info = md.info
    by_id = {d.decision_point_id: d for d in md.decisions}
    chosen = latest_verified(analyses, set(by_id))
    items = [it for dp_id, a in chosen.items() if (it := decision_value(a, by_id[dp_id])) is not None]
    items.sort(key=lambda i: i.match_clock_ms)
    players = {p.player_id: p for p in info.players}
    teams = {info.home.team_id: info.home, info.away.team_id: info.away}

    per_player: dict[str, list[DecisionValueItem]] = {}
    per_team: dict[str, list[DecisionValueItem]] = {tid: [] for tid in teams}
    for it in items:
        per_player.setdefault(it.player_id, []).append(it)
        per_team.setdefault(it.team_id, []).append(it)
    player_aggs = [aggregate(v, "player", pid, players[pid].name if pid in players else v[0].player_name,
                             v[0].team_id, min_decisions) for pid, v in per_player.items()]
    team_aggs = [aggregate(v, "team", tid, teams[tid].name if tid in teams else tid, tid, min_decisions)
                 for tid, v in per_team.items()]
    horizons = {a.simulation.config.horizon_s for a in chosen.values() if a.simulation}
    pending = set(pending_ids) - set(chosen)
    return DecisionValueReport(
        match_id=info.match_id, generated_at=utcnow().isoformat(),
        horizon_s=horizons.pop() if len(horizons) == 1 else None, min_decisions=min_decisions,
        decisions_detected=len(md.decisions), decisions_analysed=len(items),
        decisions_pending=len(pending & set(by_id)), decisions=items,
        players=sorted(player_aggs, key=_sort_key), teams=sorted(team_aggs, key=_sort_key),
        match=aggregate(items, "match", info.match_id, f"{info.home.name} v {info.away.name}", None, min_decisions),
        method=METHOD.replace(f"fewer than {MIN_DECISIONS}", f"fewer than {min_decisions}"), disclaimer=DISCLAIMER)

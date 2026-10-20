# Football Multiverse evaluation results

Generated 2026-10-20 13:04:30 by `scripts/evaluate_multiverse.py`, 3 labelled decisions, 80 paired simulations per cell, 8 sampled successor states per option for B. Agent mode: deterministic policy planner (0 live model calls). All values are modelled expected goals within the horizon on synthetic data: they measure what the model implies, not what would happen in a real match.

## A vs B vs C per decision

| Scenario | Actual | A: best vs balanced defence | C: most robust (worst case) | C: highest upside | A's choice vs counter | Optimism gap | B: top-2 flip? |
|---|---|---|---|---|---|---|---|
| shoot_vs_pass | Shoot | Dribble towards goal (1.72%) | Pass to Mbeki-Larsen (1.04%) | Dribble wide left (1.88%) | 0.16% | +1.56 pp | no |
| risky_through_ball | Pass to Saelens | Pass to El-Haddou (0.05%) | Pass to El-Haddou (0.00%) | Pass to El-Haddou (0.21%) | 0.00% | +0.05 pp | no |
| defensive_pressure | Dribble | Through ball to Thornquist (0.89%) | Through ball to Thornquist (0.68%) | Through ball to Thornquist (1.15%) | 0.68% | +0.21 pp | yes |

Optimism gap = A's chosen option valued against the balanced defence minus the same option against the defending agent's best counter (both from the adversarial matrix).

## Findings

- **Robust vs optimistic.** The adversarial planner's most robust option differed from the single-decision pick in 1/3 decisions. On average A's pick was worth 0.61 pp less modelled xG once the defence chose its best counter, so the single-decision number is optimistic; the maximin choice's worst case differed from A's pick's worst case by +0.30 pp.
- **Second-order effects.** Letting the attacker re-decide at the next decision changed the order of A's top two options in 1/3 decisions. Mean value of re-deciding (second-order minus first-order value): +1.05 pp. The successor value uses a new 10 s horizon from the successor state, so it is a ranking signal, not an additive gain.
- **Verification and grounding.** 6/6 plannings passed all deterministic checks; 36/36 narratives passed the numeric/name grounding verifier.

### B: first-order vs second-order value of the top-2 single-decision options

| Scenario | Option | First-order (A) | Second-order (re-decide at next decision) |
|---|---|---|---|
| shoot_vs_pass | Dribble towards goal | 1.72% | 6.88% |
| shoot_vs_pass | Pass to Mbeki-Larsen | 1.35% | 1.29% |
| risky_through_ball | Pass to El-Haddou | 0.05% | 0.33% |
| risky_through_ball | Through ball to Achterberg | 0.05% | 0.09% |
| defensive_pressure | Through ball to Thornquist | 0.89% | 1.11% |
| defensive_pressure | Pass to Thornquist | 0.73% | 1.41% |

Second-order values average 8 sampled successor states each, so they are indicative.

## Cost and latency

| | A single decision | B branching (top-2) | C adversarial |
|---|---|---|---|
| Rollouts per decision (mean) | 1627 | 11920 | 1093 |
| Latency (mean / p50) | 8173 ms | 51161 ms | 6002 ms (max 10094) |

C used 2.7 rounds and 17.3 matrix cells on average (bounded by 3 rounds).

## Performance

- Repeating a planning on the same frozen state: 19/19 cells served from the cache, 136 ms vs 10094 ms first time; identical matrix: True.
- Deterministic replay in a fresh service (empty cache, same seed): identical matrix: True.
- 3 plannings: 22.12 s with concurrency 1, 27.51 s with concurrency 4. Simulation is CPU-bound NumPy in one process, so concurrency mainly improves responsiveness, not throughput; scale out with more replicas.
- Peak Python heap for one branching step: 2.1 MB; largest persisted session JSON: 164.4 KB.

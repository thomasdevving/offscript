# Synthetic data and counterfactual simulator

## Pitch and coordinates

* World frame: `x ∈ [0, 105]`, `y ∈ [0, 68]` metres. Home attacks +x in the first half and −x in
  the second half (all scenarios after half-time exercise the flipped direction).
* The engine computes in an **attack frame** where the team in possession attacks x = 105; the
  conversion is a 180° rotation about the centre spot (an involution that preserves left/right).
  Conversions happen only at the boundary (snapshots in, frames/events out).

## Players, ball and motion (phase-based engine)

Play advances in **phases** (pass in flight, dribble, shot, control/hold, restart). During a phase
every player follows a closed-form, speed-bounded motion: keep the current velocity for a sampled
reaction time, then run straight at a bounded speed towards a phase target. The *same* closed-form
motion is used to resolve the phase (who reaches the ball first) and to render it at 10 Hz, so the
animation always matches the computed outcome. Tests check that no player exceeds his maximum
speed between frames (no teleports) in observed timelines and simulated rollouts.

Players have fictional names and attributes: max speed, acceleration, reaction time, technique,
finishing, dribbling, stamina. The ball has position, height (for rendering), possessor and
last-touch; passes use a decelerating ground-ball model.

## Action models

| Model | Inputs | Mechanism |
|---|---|---|
| Pass | length, ball speed (7 + 0.5·L, 9–25 m/s), deceleration, angle/length execution error (technique, pressure), receiver lead, defender positions/velocities/reaction | For 16 points along the ball path compare ball arrival time with each defender's earliest arrival (momentum, reaction, run, reach; reduced reaction when already in the lane). P(intercept) = 0.85·σ((margin − 0.15)/0.12). Near the end the defender must also beat the receiver. Late receiver → loose ball race. Heavy-touch probability under pressure. |
| Shot | distance, angle, goalkeeper position, pressure, finishing | Aim at the side the keeper leaves open; lateral noise grows with distance/pressure; over-the-bar risk; outfield blockers along the shot line (reach grows with time to the block point); goalkeeper save probability from his reachable distance before the ball passes. |
| Dribble | path, carrier speed (0.66–0.78 × max), defenders' reachability | Defenders who can reach the carrier's path with a clear margin create duels: tackle / held up / beaten probabilities depending on margin and dribbling skill. |
| Off-ball | ball destination, team shape anchors | Attackers shift with the ball, make forward runs (bounded by an approximate offside line) and pick nearby points with most room. Defenders: goalkeeper on the ball-goal line, nearest defender presses goal-side, others blend zonal shape with goal-side marking and hold a line ~13 m from goal. Targets are recomputed for each phase, so defenders **react to the alternative action**, not to the original timeline. |
| In-rollout policy | options from the current state | After the first (evaluated) action, the ball carrier chooses among shot / passes / dribbles with a softmax over cheap value estimates (completion × zone value, turnover penalty). |

Calibration targets were sanity checks against public football rules of thumb (e.g. unpressured
central shots: ≈50% from 6 m, ≈29% from 11 m, ≈7% from 20 m, ≈2% from 30 m; ≈84% pass completion
in procedural play). They are **not** fitted to data and the model is not calibrated xG.

## Primary metric

```
P(goal within H seconds | frozen snapshot, first action)      H = 10 s by default
```

The same metric, horizon, snapshot, rollout count and random streams are used for every option.
It is not xG (quality of one shot) and not xT (value of a location): it is the probability that the
whole continuation after this action produces a goal within H seconds under the model.

Secondary metrics per option: P(shot within H), P(turnover), first-action success (pass completed,
dribble succeeded, shot on target), mean time to shot, mean ball progression, outcome distribution.

### Rollout termination

A rollout ends at the first of: a goal (counted only if the ball crosses the line within the
horizon); a saved, blocked or off-target shot (rebounds are not modelled); a turnover
(interception, tackle, or loose ball won by the defenders); the ball leaving the pitch; or the
horizon with possession retained. At most 8 actions per rollout.

## Monte Carlo evaluation

* Budgets: 100 (preview), 200 (standard, default), 500 (detailed, maximum).
* **Common random numbers**: rollout *i* of every option uses the same named random streams
  (execution noise, reactions, movement, policy) derived from `SeedSequence(seed, spawn_key=(i, stream))`.
  Comparisons are **paired** (difference per rollout index), which removes much of the noise
  between options; a test shows a cloned action has exactly zero paired difference.
* Rollouts are interleaved (rollout-major) so a time-budget cut-off leaves every option with the same
  number of samples; the result is flagged `partial`.
* **Wilson 95% intervals** for every probability; normal-approximation interval for paired
  differences. These intervals describe Monte Carlo sampling error **only**.
* **Verdicts** (best alternative vs observed action): `more_promising` / `less_promising` when the
  paired interval excludes zero, `similar` when it lies within ±3 percentage points, otherwise
  `inconclusive`. OFFSCRIPT never declares a winner the evidence does not support.
* **Representative trajectory**: the medoid of the modal outcome in (end time, final ball x/y,
  number of actions) space - not the most favourable rollout. Other outcomes can be viewed as
  examples. Trajectories are re-simulated from their seed on demand, which doubles as a
  reproducibility check (verified in the verification layer).

## Multiverse extensions

The Football Multiverse (see [multiverse.md](multiverse.md)) uses the same engine with three additions.

* **Defensive strategies** (`simulation/defense.py`). A `DefenseRuntime` changes defender target
  positions (press the carrier, cover a passing lane to a named teammate, track a runner, protect
  central space, contain), multiplies defender reaction times on passes and dribbles (clipped to
  0.55-1.4) and scales the tackle probability in dribble duels (contain 0.75×, press 1.15×). Every
  strategy is validated (max 3 assignments; outfield defenders on the pitch; no duplicates; targets
  must be attackers; each defender must reach its role within 2.5 s). Speed limits still hold (tested
  for every strategy). The balanced baseline reproduces the original engine bit for bit (tested).
* **Value per cell: modelled expected goals within the horizon.** Goals within 10 s are rare, so
  binary P(goal) needs very large budgets to separate defences. Each rollout that ends in a shot
  instead contributes its *conditional* goal probability, estimated with 24 independent draws of the
  shot model from that shot state (a Rao-Blackwellised estimator of the same quantity, with lower
  variance; tested to agree with binary P(goal)). Binary P(goal), P(shot), P(turnover) and first-action
  success are still reported per cell.
* **Successor states.** `run_first_action` replays only the first action of a chosen rollout (same
  random streams as the full rollout) plus the control moment before the next decision. The engine
  state is converted into a new immutable `MatchStateSnapshot` (positions clipped to the pitch,
  velocities, carrier, possession, score, clocks). Re-replaying the same rollout gives the same child
  state (checked by `transition_reproducible`).

## Synthetic match generation

* **Scenario mode** (`/scenarios/<id>/scenario.json`, inspectable): authored starting positions in the
  attack frame, optional velocities, a scripted build-up (passes/dribbles with forced outcomes and
  optional choreographed off-ball `runs`), then an unscripted decision resolved by the engine with
  the scenario seed, then procedural continuation. Scripted events carry `scripted: true` and are
  never reported as decisions.
* **Procedural mode**: a 10-minute segment from a kick-off, every decision by the team policy,
  with turnovers, saves, blocks (loose-ball races), goal kicks, throw-ins, corners and kick-offs.
* Output: events (JSONL via `/api/matches/{id}/events.jsonl` or `scripts/precompute_demo.py`),
  tracking frames and one immutable snapshot before every on-ball action.

Reproducibility: same scenario + seed + simulator version ⇒ identical event stream, snapshots,
analyses and trajectories (all tested).

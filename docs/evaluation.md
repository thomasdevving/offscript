# Evaluation

Run `python scripts/evaluate.py` (≈3 minutes) to regenerate
[`evaluation_results.md`](evaluation_results.md) and `evaluation_results.json`. Every number below
was produced by that script on the development machine (Windows 11, Python 3.13, policy-mode
agents, 200 rollouts per option).

> **What this does and does not show.** All data is synthetic. The evaluation measures internal
> consistency, robustness and engineering behaviour. It does **not** - and cannot - show that the
> counterfactual estimates match real football.

## Summary (latest run)

| Property | Result |
|---|---|
| Decision detection recall on labelled scenario decisions | **3/4** (counter-attack dribble missed at default threshold) |
| Scripted build-up actions wrongly flagged as decisions | **0** |
| Generated candidate actions passing deterministic validation | **346/346** |
| Injected numeric corruptions caught by deterministic verification | **240/240** |
| Injected narrative corruptions caught (unsupported number, certainty language, unrelated player) | **432/432** |
| Clean, published narratives wrongly flagged | **0/144** |
| Analyses of every detected decision (4 scenarios + 10-min procedural segment) verified | **24/24**, 0 needing narrative regeneration |
| Controlled faults recovered to a verified analysis (4 faults × 3 labelled decisions) | **12/12** |
| Same decision re-analysed / trajectory replayed / scenario regenerated → identical | **yes / yes / yes** |
| Monte Carlo P(turnover) 95% interval width at 50 → 500 rollouts | 23.7% → 7.9% (≈ 1/√n) |
| State update per event (p50 / p95) | ~0.001 / 0.004 ms |
| Decision-detector work per event (p50 / p95) | ~0.001 / 5.5 ms (features only on on-ball actions) |
| Simulation, 3 options × 200 rollouts (p50 / p95) | ~2.6 / 3.9 s |
| End-to-end analysis incl. all agents, policy mode (p50 / p95) | ~2.6 / 4.0 s |

Latency with a live Foundry model adds model round-trips (up to 6 agent calls per analysis, each
bounded by `FOUNDRY_TIMEOUT_S`); it was not measured in this environment.

## Method

1. **Detection**: each scenario has a labelled decision event (`labels` in its JSON). The detector
   runs over the full event stream; recall = labelled events detected. Detections in unscripted play
   have no ground truth and are reported as counts, not as false positives.
2. **Validity**: every candidate generated before every on-ball action of the 73' scenario is
   re-validated.
3. **Verification reliability**: for every verified analysis we apply 10 random numeric corruptions
   (shift a probability, shrink an interval, alter an outcome count, alter a paired difference) and
   check rejection; for every published narrative we append an unsupported percentage, a certainty
   claim, and an unrelated player's name, and check rejection; clean narratives must pass.
4. **Recovery**: each controlled fault (`invalid_candidate`, `contradictory_claim`,
   `model_unavailable`, `simulation_timeout`) on each labelled decision; success = final status
   `verified` with the fault visible in the trace.
5. **Reproducibility**: re-run the same analysis with a fresh job; replay the representative
   trajectory from its seed; regenerate the scenario.
6. **Convergence**: same two options at 50/100/200/500 rollouts.
7. **Latency**: in-process timers (`app/services/metrics.py`) over all of the above plus ingestion of
   the 1,929-event procedural stream.

## Automated test suites

| Suite | Command | Scope |
|---|---|---|
| Backend (pytest) | `cd apps/api && pytest -q` | geometry, schemas, state engine (dedupe/reorder/replay), simulator properties (speed bounds, reproducibility, defender reaction, monotonic pressure effects), Monte Carlo (Wilson, CRN, convergence, time budget, cancellation), validation, detection, verification, full agent workflow + every recovery path + bounded retries + non-overridable verification, cache labelling, API and WebSocket |
| Optional live Foundry | `pytest -m foundry` | runs the workflow against the configured deployment (skipped without credentials) |
| Frontend unit (Vitest) | `npm run test -w apps/web` | overlay scheduling/expiry/priority, frame interpolation, i18n parity, viewer-mode rendering, workflow inspector, chart, pitch |
| End-to-end (Playwright) | `npm run e2e` | real Chromium + real backend: the acceptance flow (play → detect → verified analysis → modes → what-if → inspector → recovery → overlay JSON → Dutch → recap → scenario switch) and keyboard navigation |

Bugs found by these suites during development (and fixed) included: retry loops that did not
terminate because workflow state was copied between supersteps; players snapped onto the ball (a
"teleport") after receptions; an understated interception risk for defenders already in the lane;
narrative templates citing numbers missing from the evidence table; and a substring false positive
in the player-name check.

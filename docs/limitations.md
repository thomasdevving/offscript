# Limitations (read before quoting any number)

## Scientific

* **Counterfactuals are unobservable.** Every alternative outcome is an estimate from an explicit,
  simplified model under stated assumptions. OFFSCRIPT never states what *would* have happened, and
  the verifier rejects narratives that do.
* **Synthetic world, uncalibrated model.** The matches, players and physics are synthetic. The shot
  and pass models were sanity-checked against rules of thumb, not fitted to real data. "Modeled
  scoring probability" is not calibrated xG. Nothing here has been validated against real football
  outcomes; the evaluation measures internal consistency only.
* **Intervals are Monte Carlo error only.** Wilson intervals and paired-difference intervals say how
  precisely the model's own number is estimated, not whether the model is right.
* **Small probabilities.** Goals within 10 seconds are rare (often 0-5%). With 200 rollouts many
  comparisons are honestly `similar` or `inconclusive`; the Simulation Agent can escalate to 500.
  Paired-difference intervals use a normal approximation, which is optimistic when only a handful
  of rollouts end in a goal.
* **Simplifications.** Ground passes only (no lofted balls or crosses as distinct actions), no
  rebounds or set-piece routines, offside approximated as a limit on runs (not adjudicated), no
  fatigue dynamics inside a rollout, rule-based (not learned) team behaviour, goalkeeper does not
  distribute strategically, no referee/fouls.
* **Scenario authoring.** The four demo scenarios have authored starting positions and scripted
  build-ups (including choreographed off-ball runs in the 73' scenario) designed to create a
  meaningful decision. The decision itself and every counterfactual are resolved by the engine;
  nothing about the analysis result is scripted.
* **Detection is heuristic.** Recall on the four labelled scenario decisions is 3/4 (the counter-attack
  dribble is missed at the default threshold); analysts can request analysis of any on-ball action.

* **Decision Value Added (DVA) is only as good as the model.** It measures how far each chosen
  action falls short of the best option *the model found among the candidates it generated*. A
  better action the candidate generator never proposed counts as nothing; a model that misjudges a
  pass type misjudges every DVA built on it. DVA = 0 means "the model's best option", not "the right
  decision". Its intervals cover Monte Carlo error only, never model error.
* **DVA leans negative.** The best alternative is chosen from the same rollouts it is scored on, so
  noise that happens to favour an alternative is counted as value left on the table (the winner's
  curse). This is worst for rare goals: one simulated goal out of 200 is already "0.5 pp". The
  per-decision interval is conditional on that choice and does not include this effect; the
  evaluation measures it by re-simulating on fresh random streams (section 10 of
  [evaluation_results.md](evaluation_results.md)). A team total whose interval excludes zero is
  therefore not, on its own, evidence of poor decisions.
* **DVA aggregates are rough.** Totals add paired standard errors in quadrature, treating decisions
  as independent and using a normal approximation that is poor when goals are this rare. They are
  not fully independent: every snapshot of a synthetic match carries the match seed, so rollout *i*
  of every decision draws from the same random stream (different states consume it differently,
  but errors can correlate), and the combined interval may be too narrow. Sums depend on how many
  decisions the detector flags, so players with more on-ball time accumulate more; below 3 analysed
  decisions no numbers are shown. Only detected decisions count (manual analyst picks are excluded so
  that cherry-picked moments cannot move the totals). It is a pointer to moments worth reviewing,
  not a player rating.

* **Football Multiverse.** Defensive strategies are modelled as changed defender targets, reaction
  times and tackle probabilities, not as learned team behaviour. The response matrix covers only
  the options and strategies the agents propose (at most 3 rounds), so "most robust" means robust
  against those responses under the model. Successor states keep positions and velocities but not
  body orientation, fatigue or player intent; rebounds are still not modelled, so shots end a branch.
  Each branch realises **one** sampled continuation (representative, high-upside, defensive-success or
  random); the probabilities, not the shown sample, are the result. Values are modelled expected
  goals within the horizon (conditional Monte Carlo), not calibrated xG. Sessions are persisted as
  local JSON files (single replica). No 3D view.

## Engineering / status

* **Microsoft Foundry live path not exercised in this build environment.** The integration is
  implemented with Agent Framework's `FoundryChatClient` and managed identity, with automatic,
  labelled fallback; it needs a Foundry project endpoint + model deployment and credentials to run.
  Verify with `POST /api/diagnostics/foundry` and `pytest -m foundry`.
* **Azure deployment not executed here.** Bicep compiles cleanly (Bicep CLI 0.48.1) and CI/CD
  workflows are provided, but no Azure resources were created from this environment (no Azure
  credentials). Docker images were not built locally (Docker not installed here); CI builds the
  stack natively and the deploy workflow builds with `az acr build`.
* **In-memory store.** Matches are generated at start-up; analyses live in memory with an optional
  disk cache. A multi-replica production deployment would use a shared store (e.g. Cosmos DB or
  Blob Storage) and a queue for simulation jobs.
* **No authentication.** The demo is public and read-mostly; expensive endpoints are rate limited
  and bounded. Production use would add Entra ID auth for broadcaster tooling.
* **Video/footage.** No real video or event extraction from footage is implemented (by design:
  synthetic data only).

# Limitations (read before quoting any number)

## Scientific

* **Counterfactuals are unobservable.** Every alternative outcome is an estimate from an explicit,
  simplified model under stated assumptions. PARALLEL never states what *would* have happened, and
  the verifier rejects narratives that do.
* **Synthetic world, uncalibrated model.** The matches, players and physics are synthetic. The shot
  and pass models were sanity-checked against rules of thumb, not fitted to real data. "Modeled
  scoring probability" is not calibrated xG. Nothing here has been validated against real football
  outcomes; the evaluation measures internal consistency only.
* **Intervals are Monte Carlo error only.** Wilson intervals and paired-difference intervals say how
  precisely the model's own number is estimated, not whether the model is right.
* **Small probabilities.** Goals within 10 seconds are rare (often 0-5%). With 200 rollouts many
  comparisons are honestly `similar` or `inconclusive`; the Simulation Agent can escalate to 500.
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

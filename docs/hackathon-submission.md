# PARALLEL - Hackathon submission

**Microsoft × Premier League "Inside the Game" Hackathon 2026**
Target: Grand Prize and Best Multi-Agent System (Best Multi-Agent Orchestration).

## Elevator pitch

PARALLEL turns a live football event stream into interactive "what-if" intelligence. When a player
makes a key decision - shoot or pass, risky through ball, dribble under pressure - five specialised
AI agents built on Microsoft Agent Framework detect the moment, propose feasible alternatives,
run hundreds of paired Monte Carlo simulations from the exact frozen game state, verify every
number and claim, and explain the trade-offs for fans, analysts and broadcasters in English and
Dutch. Viewers can watch a simulated continuation of the option the player did not take - always
labelled as a model estimate, with uncertainty. *Every decision creates another game.*

## Problem

Broadcast statistics describe what happened (shot distance, xG, pass accuracy). Viewers ask a
different question: *was there a better option, and how sure can we be?* Answering it needs the
exact game state at the moment of the decision, a model of how the alternatives could have played
out, and an honest account of uncertainty - in seconds, in a form a broadcast can use.

## Solution

1. **Ingest** a real-time synthetic event stream (passes, shots, dribbles, tackles, interceptions,
   pressure, possession, tracking) with idempotent, ordered state updates.
2. **Interpret**: deterministic decision-point detection (shot with a teammate available, difficult
   pass, pressure, overloads...) from the snapshot *before* the action - no future information.
3. **Simulate**: compare the observed action with 2-3 feasible alternatives using one metric -
   P(goal within 10 s) - with common random numbers, Wilson intervals and paired comparisons.
4. **Verify**: deterministic checks on every probability, interval, comparison and claim.
5. **Explain & render**: three functionally different viewer modes, EN/NL narratives, timestamped
   machine-readable overlay instructions, what-if animation, evidence panel, match recap.

## Microsoft technologies actually used

| Technology | Use in PARALLEL | Status |
|---|---|---|
| **Microsoft Agent Framework** (`agent-framework-core` 1.22) | `Agent` per specialist, `@tool` with invocation budgets, function middleware for tool-call tracing, structured outputs, `WorkflowBuilder` with switch-case edges, executors, bounded self-loops, workflow state | Implemented and tested (CI) |
| **Microsoft Foundry** (`agent-framework-foundry` `FoundryChatClient`, Azure Identity) | Live model for all agents when `FOUNDRY_PROJECT_ENDPOINT`/`FOUNDRY_MODEL` are set; managed identity in Azure; diagnostics endpoint; optional live test | Implemented; **not exercised live in the build environment** (no credentials) - see deployment checklist |
| **Azure Container Apps** | API (HTTPS + WebSockets), managed identity, scale 1-2 | Bicep + deploy workflow; deployment pending credentials |
| **Azure Static Web Apps** | Static Next.js export | Bicep + deploy workflow; deployment pending |
| **Azure Container Registry** | API image via `az acr build` | Bicep |
| **Azure Monitor / Application Insights** (OpenTelemetry) | Traces, logs, Agent Framework instrumentation when the connection string is set | Implemented; enabled by configuration |
| **Azure Developer CLI / Bicep** | `azure.yaml`, `infra/azure/*.bicep` | Compiles (Bicep 0.48.1) |
| **GitHub Actions** | CI (lint, tests, contracts, build, Playwright e2e) and OIDC deploy | Workflows in repo |

Update the "Status" column once the deployment exists; do not claim more than is running.

## Technical innovation

* **Comparable counterfactuals**: every option starts from the same immutable snapshot (validated),
  uses the same horizon, rollout count and random streams; comparisons are paired; verdicts require
  the paired interval to exclude zero.
* **Defenders react to the alternative**, not to the original timeline: off-ball targets are
  recomputed from where the *simulated* ball goes.
* **Phase-based physics** whose closed-form motion both resolves and renders each phase: what you
  watch is exactly what was computed, and replays are bit-identical from the seed.
* **Agents decide, code computes**: agents choose questions, budgets and explanations through
  allow-listed tools; every number is a computed, evidence-referenced field.
* **Verification as an agent with teeth**: a deterministic layer the Verification Agent cannot
  override; narrative claims are checked number by number; failures route back to the right agent.
* **Real-time path**: per-event state updates in microseconds; analyses run asynchronously with
  live progress pushed to the UI; overlays are scheduled by priority and expire on match events.

## User experience

* **Casual fan**: big option cards, one probability each, plain-language story, "watch" button.
* **Tactical analyst**: interval chart, metrics table (P(goal), shot, turnover, first-action success,
  paired Δ with intervals), passing-lane/pressure annotations, evidence panel with features,
  simulation settings and all verification checks, assumptions.
* **Broadcaster**: lower-third preview on the pitch, caption, suggested timing/priority/expiry and
  the machine-readable overlay JSON.
* Agent workflow inspector, controlled recovery demo, match recap (casual/analyst), keyboard
  controls, reduced-motion support, EN/NL.

## Evaluation

See [evaluation.md](evaluation.md) (measured on synthetic data; internal consistency, not real-world
validity): 24/24 detected decisions verified; 240/240 numeric and 432/432 narrative corruptions
caught with 0/144 false positives; 12/12 controlled faults recovered; bit-identical reproducibility;
~2.6 s p50 end-to-end analysis in policy mode.

## Limitations

See [limitations.md](limitations.md). Headline: synthetic world, uncalibrated model, Monte Carlo
intervals only, authored demo scenarios, Foundry/Azure not exercised in the build environment.

## Repository and demo instructions

* Repository: https://github.com/thomasdevving/parallel (must be public at submission)
* Run locally: see [README](../README.md#quick-start) (two commands each for API and web).
* Live demo: `<add Static Web App URL after deployment>`; API health `<apiUrl>/api/health`.
* Video: `<add public YouTube/Vimeo URL>` - script in [demo-script.md](demo-script.md).

## Submission checklist

* [ ] Registered before **20 Oct 2026, 12:00 PT** (21:00 CEST)
* [ ] Public GitHub repository URL
* [ ] Demo video **under 2:00**, public on YouTube/Vimeo/Facebook Video/Youku, shows the app running,
      no unlicensed music or third-party trademarks
* [ ] Project description/pitch (above) in English
* [ ] Working project access for judges, free of charge until 10 Nov 2026 (deployed URL or clear
      local instructions; no judge credentials needed)
* [ ] Microsoft technologies listed only as actually used/configured
* [ ] Synthetic data only; fictional teams/players; original graphics (PARALLEL logo, SVG pitch);
      fonts Inter/JetBrains Mono (SIL OFL); dependencies under OSI licences; project MIT-licensed
* [ ] Original work created during the hackathon period; no sponsor support; not previously awarded
* [ ] Submitted before **27 Oct 2026, 23:59 PT** (28 Oct, 07:59 CET)

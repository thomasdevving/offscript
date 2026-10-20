# Where the implementation differs from the build brief (and why)

The brief allowed adapting details when a better approach was justified. Every deviation is listed
here so nothing is hidden.

| Brief | Implementation | Reason |
|---|---|---|
| Per-timestep (dt) physics simulation implied | **Phase-based** engine with closed-form, speed-bounded motion inside each phase | 10-20× faster (Monte Carlo of 3 options × 200 rollouts in ~2 s in pure NumPy) while the same motion law resolves *and* renders each phase, so animations match outcomes exactly. Speed bounds are enforced and tested. |
| "Lightweight charting library" | Custom SVG chart (`ComparisonChart.tsx`) | Only one chart type is needed (bars with interval whiskers); a library would add weight without benefit. |
| Agents call the LLM directly | Agents run on Agent Framework with **either** `FoundryChatClient` **or** a deterministic `PolicyChatClient` | No Foundry credentials were available in the build environment, and CI must be deterministic. The policy client keeps the real tool-calling/middleware/structured-output path and is always labelled; it is not presented as LLM output. |
| Shared state in the workflow | Typed `AnalysisWorkflowState` owned by the runtime, snapshot published to Agent Framework workflow state on each handoff | Agent Framework copies state values between supersteps; in-place counters on a copy were lost (found by tests: retry loops did not terminate). One owner + versioned snapshots keeps retries bounded and the trace consistent. |
| Narrative verification by the Verification Agent | Verification Agent runs twice: analysis checks, then narrative checks (`verify_narratives`), with Explanation ↔ Verification loop | Makes the "contradictory explanation" scenario a real agent handoff rather than a hidden function call. |
| `POST /api/analyses/{id}/simulate` | Exploratory simulation **job** (`/api/simulations/{job_id}`) separate from the verified analysis | Avoids two contradictory representations of the verified result. |
| Decision triggers list | Same triggers; `HIGH_VALUE_POSSESSION` also covers a local attacking overload (more attackers than outfield defenders within 25 m ahead of the ball) | Counter-attacks in midfield have low zone value but high viewer value. |
| Detector + agent selects decisions | Plus **manual analysis** of any on-ball action from the event feed | Detector recall is honestly < 100%; analysts can still analyse any moment. |
| Option labels like "Pass right" | Labels from the generator ("Pass to Mbeki-Larsen", "Through ball to ...", "Dribble wide right") plus **through-ball** candidates | A pass into space ahead of a runner is a distinct, important football option (and offside-bounded runners otherwise could never receive beyond the line). |
| Demo scenario story fixed in advance | Starting positions and build-up of the 73' scenario are authored (with choreographed off-ball runs); the observed shot outcome and every counterfactual come from the engine | Required to create a real "teammate in space" situation; no analysis result is scripted. Documented in `limitations.md`. |
| Static Web Apps frontend | Next.js **static export** (`output: "export"`) | No server code needed; deploys to SWA/any static host; secrets stay in the API. |
| Python 3.12+ | Pinned to 3.12 in Docker/CI; developed and tested on 3.13 | Both supported by every dependency. |
| Azure Storage / Service Bus / databases (optional) | Not used | Not justified for the demo; in-memory store + disk cache. Documented as production next steps. |

## Football Multiverse brief

| Brief | Implementation | Reason |
|---|---|---|
| Replace the Strategy Agent with an Attacking Agent | Strategy Agent kept for the single-decision analysis; **Attacking Agent added** for the Multiverse workflow | The verified single-decision analysis (and its fault-recovery tests) stays unchanged; the adversarial workflow is a separate graph with its own agents. |
| Value = P(goal within horizon) | Cells use **modelled expected goals within the horizon** (conditional Monte Carlo over shot states); binary P(goal) is still reported | Goals within 10 s are rare; binary P(goal) could not separate defensive strategies at affordable budgets. The conditional estimator targets the same quantity with lower variance (tested to agree). |
| Branch = new timeline object | **Tree of nodes** with immutable snapshots, plus a read-only `observed` node for the canonical timeline | One data structure for rewind, fork, compare and limits; the observed node makes "actual vs simulated" comparable without copying the match. |
| Defensive actions as agent-chosen player movements | Validated **strategies** (press, cover lane, track runner, protect central space, contain) applied as target/reaction/tackle changes inside the engine | Keeps defenders speed-bounded and reactive to the actual ball, and every strategy feasible (reach check); free-form movements could not be validated or simulated fairly. |
| Continue after shots | Shots end the branch (no rebounds) | The engine has no rebound model; inventing one would be an unvalidated outcome. |
| Optional 3D view | Not implemented | Time spent on correctness, tests and evaluation; the 2D pitch shows all modelled information. |
| Agents "negotiate" until equilibrium | At most 3 rounds, tabu list, 0.2 pp improvement threshold; maximin/mean/upside computed deterministically | Guarantees termination and bounded cost; the answer is a property of the matrix, not of the agents' persuasion. |

Rule discrepancies noticed while reading the official rules (follow the official rules):

* The brief mentions only the Grand Prize and the Multi-Agent prize; the official rules list
  additional category prizes (Best Use of Microsoft Foundry Project, Best Enterprise Solution,
  Best Azure Cloud Native Integration) and the prize table calls the multi-agent category
  "Best Multi-Agent Orchestration". Judges may reassign categories.
* The official rules do not mandate specific technologies; they list "hero technologies" (Foundry,
  Agent Framework, Azure services, GitHub Copilot, ...) used in Stage-One viability judging.

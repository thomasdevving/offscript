# Two-minute demo video script (draft)

Target length: **1:50** (hard limit: under 2:00). Record at 1920×1080, browser zoom 90%, dark OS
theme. Use the deployed URL (or local) with the **73' scenario**. All numbers on screen come from
the running system - do not overlay numbers in editing.

| Time | Screen | Voice-over |
|---|---|---|
| 0:00-0:12 | Close-up of the pitch: Castellane drives at the box and shoots - blocked. | "Football analytics tells you what happened. A shot, from 23 metres, blocked. But what if you could explore what *should* have happened?" |
| 0:12-0:27 | Full app, header with PARALLEL + tagline; press play from the start at 2×; event feed ticking. | "PARALLEL is a multi-agent football intelligence system. It ingests a live synthetic event stream, keeps match state, and detects the decisions that matter." |
| 0:27-0:50 | Auto-pause at the decision: frozen state, arrows for the options; agent pipeline chips turn green; casual cards appear. | "Five specialised agents on Microsoft Agent Framework take over: one decides this moment is worth analysing, a strategy agent proposes feasible alternatives, a simulation agent runs two hundred paired Monte Carlo rollouts from the exact same frozen state..." |
| 0:50-1:08 | Click "Pass to Mbeki-Larsen" → simulated continuation plays; banner "Simulated alternative - one sampled continuation". | "...and I can watch one representative continuation. Under the model, the pass led to a goal in 2% of simulations, the shot in none - it was blocked 70% of the time. A small edge, and PARALLEL says exactly how sure it is." |
| 1:08-1:30 | Open agent workflow inspector; expand Simulation Agent tool call; click "Recovery demo → Contradictory claim": Verification rejects 19% claim, Explanation retries. | "Every number is traceable. A verification agent checks the maths and every claim; here I inject a false probability - it's rejected and the explanation agent rewrites it. Models run on Microsoft Foundry, with a labelled deterministic fallback if the model is unavailable." |
| 1:30-1:45 | Switch Casual → Tactical analyst (intervals, chart, evidence) → Broadcaster (lower third + JSON) → NL. | "The same analysis becomes a fan story, an analyst breakdown with intervals and assumptions, or timestamped broadcast overlay instructions - in English or Dutch." |
| 1:45-1:55 | Logo + tagline; small text: Microsoft Agent Framework · Microsoft Foundry · Azure Container Apps · Azure Storage · Application Insights. | "One match. Countless decisions. Every decision creates another game." |

> Before recording, replace the Foundry/Azure line with what is actually configured (e.g. drop
> "Microsoft Foundry" if the deployment runs in policy mode). The app's header shows the true agent mode.

## Recommended recording sequence

1. Warm up: open the app once, play the 73' scenario to the decision so the analysis is cached
   (it will show "Replayed from cache" - fine, it is real cached output), or record live for the
   agent animation.
2. Restart (↺), set speed 2×, enable *Pause at decisions* and *Auto-analyse*.
3. Record the sequence above in one take; cut only dead time.
4. Separate take for the recovery demo (it starts a new, clearly labelled analysis).
5. Upload to YouTube/Vimeo as public/unlisted-but-public, English title and description.

## Optional Football Multiverse segment (replaces 1:08-1:30 if preferred)

| Time | Screen | Voice-over |
|---|---|---|
| 0:00-0:08 | Click **Explore in the Multiverse**; the decision tree shows the frozen decision and the actual shot (ACTUAL). | "Now I take the decision myself." |
| 0:08-0:18 | *Pass to player* → click Mbeki-Larsen → "feasible" → *Simulate this branch*; the ghost node shows the agents planning. | "An attacking agent and a defending agent plan against each other on the simulator." |
| 0:18-0:30 | The branch plays; orange arrow "cover lane"; narrative: the defence's best answer lowers the modelled chance from 1.4% to 1.0%. Switch to Tactical analyst: rounds and the response matrix. | "The defence's best answer is to cover the lane. Every cell is paired Monte Carlo; nothing is invented by a model." |
| 0:30-0:40 | Rewind, pick a dribble, then *Compare with* → split screen plays both branches in sync. | "Rewind, branch again, compare. Every decision creates another game." |

Numbers in this segment depend on the run; read them from the screen, do not script them.

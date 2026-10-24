# OFFSCRIPT demo script (1:54)

Video: screen recording `OFFSCRIPT-demo.webm` (1920×1080, 30 fps, no audio; not in the repository). Recorded on the live site with the agents
running on Microsoft Foundry; waiting time (agents thinking) is cut out. Put your webcam in the
**bottom-left corner** (max ~18% of the width): the important action is in the middle (pitch) and on
the right (analysis panel).

Pace: about 2.5 words per second, a little faster than normal conversation. **Bold** = stress.
`/` = short breath. The lines are timed to the video; if you run ahead, simply pause briefly.

---

### 0:00 - 0:10 · Landing page
*On screen: the OFFSCRIPT home page; the floating "possible futures" above the pitch; "How it works".*

> This is **OFFSCRIPT**. / Football stats tell you what happened. / We answer the question every fan
> shouts at the TV: / **was there a better option?**

### 0:10 - 0:22 · Live match → frozen decision
*On screen: the live match plays at 2×, the decision is detected and frozen, the analysis appears.*

> We follow a live match. / The moment a player makes a decision that matters, OFFSCRIPT **freezes**
> it, / and five AI agents on **Microsoft Foundry** go to work.

### 0:22 - 0:28 · Watch the alternative
*On screen: click "Pass to Mbeki-Larsen", the simulated continuation plays.*

> The shot: **zero** percent. / The pass: **two** percent. / And you can watch it play out.

### 0:28 - 0:43 · Three viewer modes
*On screen: Tactical analyst (intervals, table) → Evidence → Broadcaster (lower third + JSON).*

> Same analysis, **three audiences**. / Fans get the story. / Analysts get intervals and every piece
> of evidence. / Broadcasters get a ready-made lower third / and machine-readable overlay
> instructions.

### 0:43 - 0:54 · Agents you can audit
*On screen: the Agents tab with every agent step; "Contradictory claim" fault injected; trace.*

> Every number comes from the simulator, **never** the model. / Inject a fault on purpose: / it
> recovers, / and you see every agent, every tool call, every check.

### 0:54 - 1:04 · 3D and Player view
*On screen: 3D broadcast camera → Tactical → Player view behind Castellane.*

> In 3D: / the broadcast camera, / a tactical view, / and the **player's view**: / exactly what he saw
> when he decided to shoot.

### 1:04 - 1:20 · The Multiverse: take the decision yourself
*On screen: Multiverse, "Pass to player" → click Mbeki-Larsen → simulate → branch plays, "cover lane".*

> Now the **Multiverse**: / *you* take the decision. / I choose the pass. / An attacking and a
> defending agent now play **against each other**, / and the defence's best answer is to cover the
> passing lane.

### 1:20 - 1:26 · Agent battle
*On screen: Tactical analyst: three planning rounds and the response matrix.*

> Three rounds of strategy, / every combination simulated, / **twelve** live model calls, all checks
> passed.

### 1:26 - 1:40 · Rewind, fork, compare
*On screen: back to the decision → dribble → new branch → split screen next to what really happened.*

> Rewind to the **same frozen moment**, / try a dribble instead, / and compare any two futures side
> by side, / against what **really** happened.

### 1:40 - 1:46 · Decision Value Added
*On screen: a full 10-minute match, "Decision value" tab with the per-player table.*

> Over a whole match, that becomes a **new stat**: / Decision Value Added.

### 1:46 - 1:54 · Close
*On screen: "Who it is for", then "Take the decision yourself."*

> Goal chance left on the table, per player. / For broadcasters, analysts, fans and coaches. /
> **OFFSCRIPT**: / every decision creates another game.

---

## Facts behind the lines (so you can say them with confidence)

* All teams, players and matches are **synthetic**; every percentage is a **model estimate**
  ("under our model"), not what would really have happened. The site itself says so everywhere.
* "Five AI agents on Microsoft Foundry": Decision, Strategy, Simulation, Verification and
  Explanation agents, Microsoft Agent Framework, live on a `gpt-4.1-mini` deployment in Microsoft
  Foundry (Azure).
* 0:22: shot 0.0%, pass to Mbeki-Larsen 2.0% modelled goal chance within 10 seconds, 200 paired
  simulations each.
* 1:04: the defending agent's best answer was "Cover lane to Mbeki-Larsen"; this branch: 12 live
  model calls, 3 planning rounds, verified 12/12 checks.
* 1:40: in the 10-minute match, 18 of 18 decisions were analysed and verified.

## Before you hit record

* Speak the script once out loud against the video (it plays in any browser, VLC or Resolve). If
  your editor does not accept WebM, convert it to MP4 with HandBrake (free).
* Want a different order or more time for a scene? Say so: the recording is a script, so a new
  version takes 10 minutes.

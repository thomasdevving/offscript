# OFFSCRIPT demo script (1:59)

Video: screen recording `OFFSCRIPT-demo.webm` (1920×1080, 30 fps, no audio; not in the repository). Recorded on the live site with the agents
running on Microsoft Foundry; most waiting time (agents thinking) is cut out, but you see them at work
twice on purpose. Put your webcam in the **bottom-left corner** (max ~18% of the width): the important
action is in the middle (pitch) and on the right (analysis panel).

Pace: about 2.4 words per second, a little faster than normal conversation. **Bold** = stress.
`/` = short breath. The lines are timed to the video; if you run ahead, simply pause briefly.

---

### 0:00 - 0:09 · Landing page
*On screen: the OFFSCRIPT home page; the floating "possible futures" above the pitch; "How it works".*

> This is **OFFSCRIPT**. / Stats tell you what happened. / We answer what every fan shouts at the
> TV: / **was there a better option?**

### 0:09 - 0:27 · Live match → agents at work → verified
*On screen: the match plays at 2×, the decision is frozen, the "Agents at work" log fills (Decision →
Strategy → Simulation agent), then the verified analysis appears.*

> We follow a live match. / The moment a player makes a decision that matters, OFFSCRIPT **freezes**
> it. / Five AI agents on **Microsoft Foundry** go to work, / and you watch them live: / which agent,
> which tool, which handoff. / And then: / a **verified** answer.

### 0:27 - 0:34 · Watch the alternative
*On screen: click "Pass to Mbeki-Larsen", the simulated continuation plays.*

> The shot: **zero** percent. / The pass: **two** percent. / And you can watch it play out.

### 0:34 - 0:48 · Three viewer modes
*On screen: Tactical analyst (intervals, table) → Evidence → Broadcaster (lower third + JSON).*

> Same analysis, **three audiences**. / Fans get the story. / Analysts get intervals and every piece
> of evidence. / Broadcasters get a ready-made lower third / and machine-readable overlay
> instructions.

### 0:48 - 1:01 · Stress test: break it on purpose
*On screen: Agents tab, "False number in the story" → the three-step card: what we broke, how it was
caught, result.*

> Can you trust it? / We **break it on purpose**: / a false number in the story. / The Verification
> agent checks every number, / **rejects** it, / and the story is rewritten.

### 1:01 - 1:11 · 3D and Player view
*On screen: 3D broadcast camera → Tactical → Player view behind Castellane.*

> In 3D: / the broadcast camera, / a tactical view, / and the **player's view**: / exactly what he saw
> when he decided to shoot.

### 1:11 - 1:29 · The Multiverse: take the decision yourself
*On screen: Multiverse, "Pass to player" → click Mbeki-Larsen → simulate → "Agents planning" with the
response matrix filling live → the branch plays.*

> Now the **Multiverse**: / *you* take the decision. / I choose the pass. / An attacking and a
> defending agent now play **against each other**, / and you see every combination being simulated
> live. / The defence's best answer: / cover the passing lane.

### 1:29 - 1:34 · Agent battle
*On screen: Tactical analyst: three planning rounds and the response matrix.*

> Three rounds of strategy, / every number from the simulator, / all checks passed.

### 1:34 - 1:48 · Rewind, fork, compare
*On screen: back to the decision → dribble → new branch → split screen next to what really happened.*

> Rewind to the **same frozen moment**, / try a dribble instead, / and compare any two futures side
> by side, / against what **really** happened.

### 1:48 - 1:53 · Decision Value Added
*On screen: a full 10-minute match, "Decision value" tab with the per-player table.*

> Over a whole match, that becomes a **new stat**: / Decision Value Added.

### 1:53 - 1:59 · Close
*On screen: "Who it is for", then "Take the decision yourself."*

> For broadcasters, analysts, fans and coaches. / **OFFSCRIPT**: / every decision creates another
> game.

---

## Facts behind the lines (so you can say them with confidence)

* All teams, players and matches are **synthetic**; every percentage is a **model estimate**
  ("under our model"), not what would really have happened. The site itself says so everywhere.
* "Five AI agents on Microsoft Foundry": Decision, Strategy, Simulation, Verification and
  Explanation agents, Microsoft Agent Framework, live on a `gpt-4.1-mini` deployment in Microsoft
  Foundry (Azure).
* 0:09: the "Agents at work" log is real: it streams each agent start, tool call and handoff over
  WebSocket while the live model works. The wait was shortened in the edit.
* 0:27: shot 0.0%, pass to Mbeki-Larsen 2.0% modelled goal chance within 10 seconds, 200 paired
  simulations each.
* 0:48: the stress test runs on a **copy**; the real analysis is never touched. In this take the
  false number was 19.3%; the Verification agent found no evidence field for it, and the story was
  replaced by a verified version before it reached the screen.
* 1:11: the defending agent's best answer was "Cover lane to Mbeki-Larsen"; this branch: 3 planning
  rounds, 12 live model calls, verified 12/12 checks.
* 1:48: in the 10-minute match, 18 of 18 decisions were analysed and verified; Luca Ferreira-Holm
  left the most modelled goal chance on the table (about 1.5 percentage points across 3 decisions in the latest take; the exact value varies slightly per live run).

## Before you hit record

* Speak the script once out loud against the video (it plays in any browser, VLC or Resolve). If
  your editor does not accept WebM, convert it to MP4 with HandBrake (free).
* Want a different order or more time for a scene? Say so: the recording is a script, so a new
  version takes about 10 minutes.

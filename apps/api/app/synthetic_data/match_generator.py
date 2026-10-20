"""Synthetic match generator.

Plays continuous football with the same phase engine used for counterfactual rollouts:
possessions, turnovers, shots, goals and restarts. Produces

* an observed tracking timeline (world coordinates, fixed frame rate),
* an ordered, immutable event stream (MatchEvent, JSONL-serialisable), and
* an immutable MatchStateSnapshot taken immediately *before* every on-ball action.

Two modes share this code path:
* scenario mode: a scripted build-up (forced outcomes, flagged `scripted=True` on the events)
  followed by an unscripted decision and procedural continuation;
* procedural mode: no script, every decision is made by the stochastic team policy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..models.common import SIMULATOR_VERSION, format_clock
from ..models.events import EventDetails, EventType, MatchEvent, TrackingFrame
from ..models.match import MatchInfo, Player, SimulationSettings
from ..models.state import BallState, MatchStateSnapshot, PlayerState
from ..simulation import geometry as g
from ..simulation.engine import BallPath, Engine, EngineState, Motion, PhaseResult, RolloutRng, pressure_count
from ..simulation.rollout import _Recorder, profile_from_player
from .roster import (
    AWAY,
    HOME,
    IN_POSSESSION,
    KICKOFF,
    OUT_OF_POSSESSION,
    ROSTER,
    TEAMS,
    starters,
    template_positions,
)


@dataclass
class RawEvent:
    t: float
    order: int
    event_type: EventType
    team_id: str | None
    player_ids: list[str]
    x: float | None
    y: float | None
    end_x: float | None = None
    end_y: float | None = None
    details: dict = field(default_factory=dict)
    snapshot_key: int | None = None


@dataclass
class GeneratedMatch:
    info: MatchInfo
    events: list[MatchEvent]
    frames: list[TrackingFrame]
    snapshots: dict[str, MatchStateSnapshot]
    roster: dict[str, Player]
    decision_event_ids: list[str] = field(default_factory=list)
    scripted_event_ids: list[str] = field(default_factory=list)


class MatchGenerator:
    def __init__(
        self,
        *,
        match_id: str,
        title: str,
        seed: int,
        period: int,
        start_clock_ms: int,
        score: dict[str, int],
        attacking_team: str,
        positions_attack_frame: dict[str, tuple[float, float]] | None,
        velocities_attack_frame: dict[str, tuple[float, float]] | None,
        carrier_id: str | None,
        frame_hz: int = 10,
        scenario_id: str | None = None,
        description: str = "",
        mode: str = "scenario",
    ):
        self.match_id = match_id
        self.title = title
        self.seed = seed
        self.period = period
        self.start_clock_ms = start_clock_ms
        self.score = dict(score)
        self.initial_score = dict(score)
        self.scenario_id = scenario_id
        self.description = description
        self.mode = mode
        self.frame_hz = frame_hz
        # Home attacks +x in the first half and -x in the second half.
        self.home_dir = 1 if period == 1 else -1
        self.dir_of = {HOME.team_id: self.home_dir, AWAY.team_id: -self.home_dir}
        self.on_pitch = starters(HOME.team_id) + starters(AWAY.team_id)
        self.off_pitch = [p.player_id for p in ROSTER.values() if not p.starting]
        def_team = AWAY.team_id if attacking_team == HOME.team_id else HOME.team_id
        profiles = [profile_from_player(p) for p in self.on_pitch]
        is_att = np.array([p.team_id == attacking_team for p in self.on_pitch])
        if positions_attack_frame is None:
            positions_attack_frame = self._template_frame(attacking_team, KICKOFF, KICKOFF)
        pos = np.array([positions_attack_frame[p.player_id] for p in self.on_pitch], dtype=float)
        vel = np.array([(velocities_attack_frame or {}).get(p.player_id, (0.0, 0.0)) for p in self.on_pitch], dtype=float)
        carrier = next(i for i, p in enumerate(self.on_pitch) if p.player_id == carrier_id) if carrier_id else None
        ball = pos[carrier].copy() if carrier is not None else np.array(g.CENTRE)
        self.state = EngineState(
            profiles=profiles, is_att=is_att, pos=pos, vel=vel, anchors=pos.copy(), ball=ball, ball_ref=ball.copy(),
            carrier=carrier, t=0.0, direction=self.dir_of[attacking_team], att_team=attacking_team, def_team=def_team,
        )
        self.recorder = _Recorder(self.state, dt=1.0 / frame_hz)
        self.engine = Engine(record=self.recorder)
        self.raw: list[RawEvent] = []
        self.snapshots_raw: list[MatchStateSnapshot] = []
        self.action_counter = 0
        self._order = 0
        self.policy_rng = np.random.default_rng(np.random.SeedSequence(entropy=seed, spawn_key=(424242,)))
        self.decision_keys: list[int] = []
        self.scripted_orders: list[int] = []

    # ------------------------------------------------------------------ helpers
    def _template_frame(self, attacking_team: str, att_tpl: dict, def_tpl: dict) -> dict[str, tuple[float, float]]:
        out: dict[str, tuple[float, float]] = {}
        for team_id in (HOME.team_id, AWAY.team_id):
            players = [p for p in self.on_pitch if p.team_id == team_id]
            tpl = template_positions(players, att_tpl if team_id == attacking_team else def_tpl)
            for pid, (x, y) in tpl.items():
                out[pid] = (x, y) if team_id == attacking_team else (g.PITCH_LENGTH - x, g.PITCH_WIDTH - y)
        return out

    def _set_template_anchors(self) -> None:
        tpl = self._template_frame(self.state.att_team, IN_POSSESSION, OUT_OF_POSSESSION)
        self.state.anchors = np.array([tpl[p.player_id] for p in self.state.profiles], dtype=float)
        self.state.ball_ref = np.array(g.CENTRE)

    def _pid(self, i: int | None) -> str | None:
        return None if i is None else self.state.profiles[i].player_id

    def _team_of(self, pid: str | None) -> str | None:
        return ROSTER[pid].team_id if pid else None

    def _w(self, xy) -> tuple[float, float]:
        w = self.state.to_world(np.asarray(xy, dtype=float))
        return round(float(w[0]), 2), round(float(w[1]), 2)

    def _emit(self, t: float, etype: EventType, players: list[str], pos=None, end=None, team_id: str | None = None,
              snapshot_key: int | None = None, **details) -> RawEvent:
        x = y = ex = ey = None
        if pos is not None:
            x, y = self._w(pos)
        if end is not None:
            ex, ey = self._w(end)
        self._order += 1
        ev = RawEvent(t=t, order=self._order, event_type=etype,
                      team_id=team_id or (self._team_of(players[0]) if players else None), player_ids=players,
                      x=x, y=y, end_x=ex, end_y=ey, details={k: v for k, v in details.items() if v is not None},
                      snapshot_key=snapshot_key)
        self.raw.append(ev)
        return ev

    def capture(self) -> int:
        s = self.state
        wpos = s.to_world(s.pos)
        wvel = s.vel * s.direction
        players = [
            PlayerState(player_id=p.player_id, team_id=p.team_id, x=round(float(wpos[i, 0]), 3),
                        y=round(float(wpos[i, 1]), 3), vx=round(float(wvel[i, 0]), 3), vy=round(float(wvel[i, 1]), 3),
                        facing=round(math.atan2(float(wvel[i, 1]), float(wvel[i, 0])), 3))
            for i, p in enumerate(s.profiles)
        ]
        bx, by = self._w(s.ball)
        snap = MatchStateSnapshot(
            snapshot_id=f"tmp-{len(self.snapshots_raw)}",
            match_id=self.match_id,
            sim_time_ms=int(round(s.t * 1000)),
            match_clock_ms=self.start_clock_ms + int(round(s.t * 1000)),
            period=self.period,
            possession_team_id=s.att_team,
            attack_direction={s.att_team: s.direction, s.def_team: -s.direction},
            ball=BallState(x=bx, y=by, possessor_id=self._pid(s.carrier), last_touch_id=self._pid(s.carrier)),
            players=players,
            off_pitch_player_ids=list(self.off_pitch),
            score=dict(self.score),
            seed=self.seed,
            simulator_version=SIMULATOR_VERSION,
        )
        self.snapshots_raw.append(snap)
        return len(self.snapshots_raw) - 1

    # ------------------------------------------------------------------ phases
    def _reset_phase(self, duration: float, ball_to: np.ndarray, targets_tpl: dict[str, tuple[float, float]],
                     overrides: dict[int, np.ndarray] | None = None) -> None:
        s = self.state
        targets = np.array([targets_tpl[p.player_id] for p in s.profiles], dtype=float)
        for i, t in (overrides or {}).items():
            targets[i] = t
        speeds = s.vmax * 0.55
        dist = float(np.linalg.norm(ball_to - s.ball))
        motion = Motion(s.t, duration, s.pos.copy(), s.vel.copy(), np.full(s.n, 0.2), targets, speeds,
                        BallPath("flight", s.ball.copy(), ball_to.copy(), v0=max(dist / duration, 0.01), decel=0.0,
                                 total_dist=dist))
        self.engine._commit(s, motion)
        s.ball = ball_to.copy()
        for i, t in (overrides or {}).items():
            s.pos[i] = t
        s.vel[:] = 0.0

    def _turnover(self, new_carrier: int, t: float, pos, reason: str) -> None:
        lost_by = self._pid(self.state.carrier)
        self.state.flip_possession(new_carrier)
        self._set_template_anchors()
        self.state.ball = self.state.pos[new_carrier].copy()
        self._emit(t, EventType.POSSESSION_CHANGED, [self._pid(new_carrier)], pos=self.state.ball,
                   team_id=self.state.att_team, outcome=reason, lost_by_id=lost_by, won_by_id=self._pid(new_carrier))

    def _kickoff(self) -> None:
        s = self.state
        # Conceding team (currently defending) kicks off: flip to their frame first.
        s.flip_possession(None)
        tpl = self._template_frame(s.att_team, KICKOFF, KICKOFF)
        st = next(i for i, p in enumerate(s.profiles) if s.is_att[i] and p.role == "ST")
        centre = np.array(g.CENTRE)
        self._reset_phase(7.0, centre, tpl, overrides={st: centre - np.array([0.4, 0.0])})
        s.carrier = st
        s.ball = s.pos[st].copy()
        self._set_template_anchors()
        self._emit(s.t, EventType.RESTART, [self._pid(st)], pos=s.ball, team_id=s.att_team, restart_type="kick_off")

    def _goal_kick(self, flip: bool = True) -> None:
        s = self.state
        if flip:
            s.flip_possession(None)
        gk = s.gk(attacking=True)
        spot = np.array([5.5, g.PITCH_WIDTH / 2 + float(self.policy_rng.choice([-7.0, 7.0]))])
        tpl = self._template_frame(s.att_team, IN_POSSESSION, OUT_OF_POSSESSION)
        tpl = {k: (max(v[0] - 18, 3.0), v[1]) for k, v in tpl.items()}
        self._reset_phase(4.0, spot, tpl, overrides={gk: spot - np.array([0.5, 0.0])})
        s.carrier = gk
        s.ball = s.pos[gk].copy()
        self._set_template_anchors()
        self._emit(s.t, EventType.RESTART, [self._pid(gk)], pos=s.ball, team_id=s.att_team, restart_type="goal_kick")

    def _restart_after_out(self, out_pt: np.ndarray) -> None:
        """Ball left the pitch off the attacking team: the other team restarts.

        `out_pt` is in the attack frame of the team that lost the ball. Touchline exits
        give a throw-in, end-line exits a goal kick or a corner.
        """
        s = self.state
        s.flip_possession(None)
        pt = g.arr_to_attack_frame(out_pt, -1)
        restart = "throw_in"
        if pt[0] <= 0.6 or pt[0] >= g.PITCH_LENGTH - 0.6:
            if pt[0] < g.PITCH_LENGTH / 2:
                self._goal_kick(flip=False)
                return
            restart = "corner"
            pt = np.array([g.PITCH_LENGTH - 0.5, 0.5 if pt[1] < g.PITCH_WIDTH / 2 else g.PITCH_WIDTH - 0.5])
        else:
            pt = np.array([pt[0], 0.3 if pt[1] < g.PITCH_WIDTH / 2 else g.PITCH_WIDTH - 0.3])
        att = np.array([i for i in s.att_idx() if s.profiles[i].role != "GK"])
        k = int(att[np.argmin(np.linalg.norm(s.pos[att] - pt, axis=1))])
        tpl = {p.player_id: (float(s.pos[i][0]), float(s.pos[i][1])) for i, p in enumerate(s.profiles)}
        self._reset_phase(3.0, pt, tpl, overrides={k: pt.copy()})
        s.carrier = k
        s.ball = pt.copy()
        self._set_template_anchors()
        self._emit(s.t, EventType.RESTART, [self._pid(k)], pos=s.ball, team_id=s.att_team, restart_type=restart)

    def _loose_after_block(self, pt: np.ndarray, rng: RolloutRng) -> None:
        s = self.state
        u = float(rng[0].random())
        pool = s.def_idx() if u < 0.6 else s.att_idx()
        pool = np.array([i for i in pool if s.profiles[i].role != "GK"])
        k = int(pool[np.argmin(np.linalg.norm(s.pos[pool] - pt, axis=1))])
        targets = s.pos.copy()
        targets[k] = pt
        speeds = s.vmax * 0.6
        speeds[k] = s.vmax[k]
        d = float(np.linalg.norm(s.pos[k] - pt))
        dur = max(0.4, d / s.vmax[k] + 0.2)
        motion = Motion(s.t, dur, s.pos.copy(), s.vel.copy(), np.full(s.n, 0.2), targets, speeds,
                        BallPath("static", pt.copy(), pt.copy()))
        self.engine._commit(s, motion)
        s.pos[k] = pt
        if s.is_att[k]:
            s.carrier = k
            s.ball = pt.copy()
        else:
            self._turnover(k, s.t, pt, "loose_ball")

    # ------------------------------------------------------------------ main loop
    def _event_from_engine(self, ev: dict, t: float, snap_key: int | None) -> None:
        et = EventType(ev["type"])
        det = dict(ev.get("detail", {}))
        kw: dict = {}
        if et == EventType.PASS_ATTEMPTED:
            kw = {"pass_length_m": round(det.get("length", 0.0), 2), "ball_speed_mps": round(det.get("speed", 0.0), 2)}
            if len(ev["players"]) > 1:
                kw["intended_receiver_id"] = ev["players"][1]
        elif et == EventType.PASS_COMPLETED:
            kw = {"receiver_id": ev["players"][1] if len(ev["players"]) > 1 else None, "outcome": det.get("reason")}
        elif et in (EventType.PASS_FAILED, EventType.DRIBBLE_FAILED):
            kw = {"outcome": det.get("reason", "failed")}
        elif et in (EventType.INTERCEPTION,):
            kw = {"won_by_id": ev["players"][0]}
        elif et in (EventType.TACKLE, EventType.SHOT_BLOCKED, EventType.SHOT_SAVED, EventType.PRESSURE_APPLIED):
            kw = {"won_by_id": ev["players"][0], "lost_by_id": ev["players"][1] if len(ev["players"]) > 1 else None}
        elif et == EventType.SHOT_ATTEMPTED:
            kw = {"shot_speed_mps": round(det.get("speed", 0.0), 2), "distance_to_goal_m": round(det.get("distance", 0.0), 2)}
        self._emit(t, et, list(ev["players"]), pos=ev["pos"], end=ev.get("end"), snapshot_key=snap_key, **kw)

    def _do_action(self, kind: str, receiver: int | None, target: np.ndarray | None, forced: str | None,
                   scripted: bool, is_decision: bool) -> PhaseResult:
        s = self.state
        c = s.carrier
        assert c is not None
        snap_key = self.capture()
        if is_decision:
            self.decision_keys.append(snap_key)
        rng = RolloutRng(self.seed, 100000 + self.action_counter)
        self.action_counter += 1
        t0 = s.t
        d_def = np.linalg.norm(s.pos[s.def_idx()] - s.pos[c], axis=1)
        nearest = float(d_def.min()) if len(d_def) else 99.0
        press = pressure_count(s, c, 4.0)
        extra: dict = {"pressure_count": press, "nearest_defender_m": round(nearest, 2)}
        if kind == "shoot":
            extra["modeled_scoring_probability"] = round(self.engine.shot_probability(s, c, 400, seed=self.seed), 4)
        if kind == "pass" and receiver is not None:
            e = self.engine.expected_pass(s, c, receiver)
            extra["pass_difficulty"] = round(1 - e["completion_est"], 4)
        if nearest < 2.0:
            j = int(s.def_idx()[np.argmin(d_def)])
            self._emit(t0, EventType.PRESSURE_APPLIED, [self._pid(j), self._pid(c)], pos=s.pos[j],
                       won_by_id=self._pid(j), lost_by_id=self._pid(c))
        if kind == "shoot":
            res = self.engine.resolve_shot(s, c, rng)
        elif kind == "pass":
            res = self.engine.resolve_pass(s, c, receiver, target if receiver is None else None, rng, forced=forced)
        else:
            assert target is not None
            res = self.engine.resolve_dribble(s, c, target, rng, forced=forced)
        for k, ev in enumerate(res.events):
            t_ev = t0 if k == 0 else s.t
            self._event_from_engine(ev, t_ev, snap_key if k == 0 else None)
            last = self.raw[-1]
            if k == 0:
                last.details.update({k2: v for k2, v in extra.items() if v is not None})
            if scripted:
                last.details["scripted"] = True
                self.scripted_orders.append(last.order)
        return res

    def _after(self, res: PhaseResult, rng_seed_key: int) -> None:
        s = self.state
        rng = RolloutRng(self.seed, 500000 + rng_seed_key)
        if res.kind == "shot":
            if res.outcome == "goal":
                self.score[s.att_team] += 1
                # The engine emitted the GOAL event (with the scorer); attach the new score to it.
                self.raw[-1].details.update(score_home=self.score[HOME.team_id], score_away=self.score[AWAY.team_id])
                self._kickoff()
            elif res.outcome == "saved":
                gk = s.gk(attacking=False)
                self._turnover(gk, s.t, s.ball, "save")
                self.engine.control_phase(s, 1.5, rng[3])
            elif res.outcome == "blocked":
                self._loose_after_block(s.ball.copy(), rng)
            else:
                self._emit(s.t, EventType.BALL_OUT_OF_PLAY, [], pos=s.ball, team_id=None)
                self._goal_kick()
            return
        if res.turnover_to is not None:
            self._turnover(res.turnover_to, s.t, s.pos[res.turnover_to], res.outcome)
            return
        if res.outcome == "out_of_play":
            self._restart_after_out(s.ball.copy())
            return
        s.carrier = res.new_carrier
        s.ball = s.pos[s.carrier].copy()

    def run(self, script: list[dict], continuation_s: float, decision_markers: bool = True) -> GeneratedMatch:
        s = self.state
        self._emit(0.0, EventType.MATCH_STARTED, [], pos=s.ball, team_id=None,
                   score_home=self.score[HOME.team_id], score_away=self.score[AWAY.team_id],
                   outcome="segment_start")
        script = list(script)
        end_t: float | None = None
        n = 0
        while True:
            n += 1
            if n > 2000:
                break
            if not script:
                if end_t is None:
                    end_t = s.t + continuation_s
                if s.t >= end_t:
                    break
            step = script.pop(0) if script else None
            if s.carrier is None:
                break
            if step and step["type"] == "control":
                self.engine.control_phase(s, float(step.get("duration", 0.6)), RolloutRng(self.seed, 900000 + n)[3])
                continue
            self.engine.run_overrides = {
                s.index(pid): np.array(xy, dtype=float) for pid, xy in (step or {}).get("runs", {}).items()
            }
            if step is not None:
                kind, receiver, target, forced, is_dec = self._script_action(step)
                scripted = step["type"] != "decision"
            else:
                kind, receiver, tgt, _ = self.engine.choose_action(s, self.policy_rng, temperature=0.025)
                target = tgt if kind == "dribble" else None
                forced, scripted, is_dec = None, False, False
            res = self._do_action(kind, receiver, target, forced, scripted, is_dec)
            self._after(res, n)
            if res.turnover_to is not None or s.carrier is None:
                self.engine.run_overrides = {}
            if s.carrier is not None and (not script or script[0]["type"] != "control"):
                hold = 0.35 if step is not None and step["type"] != "decision" else float(self.policy_rng.uniform(0.5, 1.3))
                self.engine.control_phase(s, hold, RolloutRng(self.seed, 800000 + n)[3])
        self._emit(s.t, EventType.MATCH_ENDED, [], pos=s.ball, team_id=None,
                   score_home=self.score[HOME.team_id], score_away=self.score[AWAY.team_id], outcome="segment_end")
        return self._finalize()

    def _script_action(self, step: dict):
        s = self.state
        actor = s.index(step["actor"])
        if actor != s.carrier:
            raise ValueError(f"Scripted actor {step['actor']} does not have the ball")
        action = step if step["type"] != "decision" else step["action"]
        kind = action["type"] if step["type"] == "decision" else step["type"]
        receiver = s.index(action["target"]) if action.get("target") else None
        target = np.array(action["to"], dtype=float) if action.get("to") else None
        forced = None
        if step["type"] != "decision":
            forced = {"pass": "complete", "dribble": "success"}.get(kind)
        return kind, receiver, target, forced, step["type"] == "decision"

    # ------------------------------------------------------------------ output
    def _finalize(self) -> GeneratedMatch:
        frames = self.recorder.frames
        # Low-rate position update events (1 Hz) derived from the tracking frames.
        step = self.frame_hz
        for k in range(0, len(frames), step):
            f = frames[k]
            t = f.t_ms / 1000
            self.raw.append(RawEvent(t=t, order=10_000_000 + k, event_type=EventType.BALL_POSITION_UPDATED,
                                     team_id=None, player_ids=[], x=f.ball[0], y=f.ball[1]))
            self.raw.append(RawEvent(t=t, order=10_000_001 + k, event_type=EventType.PLAYER_POSITION_UPDATED,
                                     team_id=None, player_ids=[], x=None, y=None,
                                     details={"positions": dict(f.players)}))
        self.raw.sort(key=lambda e: (round(e.t, 3), e.order))
        events: list[MatchEvent] = []
        snap_ids = {k: f"{self.match_id}-snap-{k:04d}" for k in range(len(self.snapshots_raw))}
        snap_source: dict[int, str] = {}
        decision_event_ids: list[str] = []
        scripted_ids: list[str] = []
        for seq, r in enumerate(self.raw, start=1):
            eid = f"{self.match_id}-ev-{seq:05d}"
            ms = int(round(r.t * 1000))
            sid = snap_ids[r.snapshot_key] if r.snapshot_key is not None else None
            if r.snapshot_key is not None:
                snap_source[r.snapshot_key] = eid
                if r.snapshot_key in self.decision_keys:
                    decision_event_ids.append(eid)
            if r.order in self.scripted_orders:
                scripted_ids.append(eid)
            events.append(MatchEvent(
                event_id=eid, match_id=self.match_id, seq=seq, sim_time_ms=ms,
                match_clock_ms=self.start_clock_ms + ms, event_type=r.event_type, team_id=r.team_id,
                player_ids=r.player_ids, x=r.x, y=r.y, end_x=r.end_x, end_y=r.end_y, snapshot_id=sid,
                details=EventDetails(**r.details),
            ))
        snapshots = {}
        for k, snap in enumerate(self.snapshots_raw):
            snapshots[snap_ids[k]] = snap.model_copy(update={"snapshot_id": snap_ids[k],
                                                             "source_event_id": snap_source.get(k)})
        duration_ms = frames[-1].t_ms if frames else 0
        info = MatchInfo(
            match_id=self.match_id,
            title=self.title,
            scenario_id=self.scenario_id,
            home=HOME,
            away=AWAY,
            players=list(ROSTER.values()),
            settings=SimulationSettings(mode=self.mode, seed=self.seed, simulator_version=SIMULATOR_VERSION,
                                        frame_rate_hz=self.frame_hz, description=self.description),
            period=self.period,
            start_clock_ms=self.start_clock_ms,
            end_clock_ms=self.start_clock_ms + duration_ms,
            duration_ms=duration_ms,
            initial_score=self.initial_score,
            final_score=dict(self.score),
            home_attack_direction_first_half=1,
            description=self.description,
            tags=[self.mode, f"starts {format_clock(self.start_clock_ms)}"],
        )
        return GeneratedMatch(info=info, events=events, frames=frames, snapshots=snapshots, roster=dict(ROSTER),
                              decision_event_ids=decision_event_ids, scripted_event_ids=scripted_ids)


__all__ = ["MatchGenerator", "GeneratedMatch", "TEAMS"]

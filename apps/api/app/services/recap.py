"""Automated match recap grounded in recorded events and verified analyses."""

from __future__ import annotations

from ..match_state.engine import MatchStateEngine
from ..models.analysis import CounterfactualAnalysis
from ..models.common import Language, format_clock, new_id, utcnow
from ..models.events import EventType
from ..models.recap import MomentumWindow, PlayerPerformance, Recap, RecapFormat, RecapItem
from ..verification.evidence import pct
from .store import MatchData

SHOT_OUTCOMES = {EventType.GOAL: ("scored", "scoorde"), EventType.SHOT_SAVED: ("was saved", "werd gestopt"),
                 EventType.SHOT_BLOCKED: ("was blocked", "werd geblokt"),
                 EventType.SHOT_MISSED: ("went wide", "ging naast")}

DISCLAIMER = {
    "en": "Synthetic match with fictional teams. Counterfactual insights are estimates from OFFSCRIPT's simulation model "
          "under stated assumptions, not statements about what would have happened.",
    "nl": "Synthetische wedstrijd met fictieve teams. Alternatieve scenario's zijn schattingen van het simulatiemodel "
          "van OFFSCRIPT onder vermelde aannames, geen uitspraken over wat er gebeurd zou zijn.",
}


def build_recap(md: MatchData, analyses: list[CounterfactualAnalysis], language: Language = "en") -> Recap:
    L = language
    info = md.info
    engine = MatchStateEngine(info)
    view = engine.replay(md.events)
    short = {p.player_id: p.short_name for p in info.players}
    home, away = info.home, info.away
    fs = info.final_score
    score_line = f"{home.name} {fs[home.team_id]}-{fs[away.team_id]} {away.name}"
    events = md.events
    key: list[RecapItem] = []
    ref_events: list[str] = []
    for i, e in enumerate(events):
        if e.event_type != EventType.SHOT_ATTEMPTED:
            continue
        outcome = next((x for x in events[i + 1:i + 6] if x.event_type in SHOT_OUTCOMES), None)
        if outcome is None:
            continue
        verb = SHOT_OUTCOMES[outcome.event_type][0 if L == "en" else 1]
        shooter = short.get(e.player_ids[0], "?")
        q = e.details.modeled_scoring_probability
        qtxt = (f" (modeled chance {pct(q, L)})" if L == "en" else f" (gemodelleerde kans {pct(q, L)})") if q else ""
        text = (f"{shooter}'s shot {verb}{qtxt}." if L == "en" else f"Schot van {shooter} {verb}{qtxt}.")
        key.append(RecapItem(text=text, match_clock=format_clock(e.match_clock_ms), event_ids=[e.event_id,
                             outcome.event_id], kind="goal" if outcome.event_type == EventType.GOAL else "shot"))
        ref_events += [e.event_id, outcome.event_id]

    analysed = {a.decision_point_id for a in analyses if a.status == "verified"}
    for dp in md.decisions:
        if dp.decision_point_id in analysed:
            continue
        trig = ", ".join(t.value.lower().replace("_", " ") for t in dp.triggers[:2])
        outcome = dp.actual_outcome.lower().replace("_", " ")
        text = (f"Key decision: {short.get(dp.actor_id, '?')} - {dp.actual_action.label.replace(' (actual)', '')} "
                f"({outcome}; {trig})." if L == "en" else
                f"Sleutelmoment: {short.get(dp.actor_id, '?')} - {dp.actual_action.label.replace(' (actual)', '')} "
                f"({outcome}; {trig}).")
        key.append(RecapItem(text=text, match_clock=format_clock(dp.match_clock_ms), event_ids=[dp.event_id],
                             kind="decision"))
        ref_events.append(dp.event_id)
    key.sort(key=lambda k: k.match_clock or "")

    insights: list[RecapItem] = []
    ref_an: list[str] = []
    for a in analyses:
        if a.status != "verified":
            continue
        nar = next((n for n in a.narratives if n.audience == "casual" and n.language == L), None)
        dp = md.decisions and next((d for d in md.decisions if d.decision_point_id == a.decision_point_id), None)
        if nar is None or not dp:
            continue
        insights.append(RecapItem(text=f"{nar.headline} {nar.body}", match_clock=format_clock(dp.match_clock_ms),
                                  event_ids=[dp.event_id], analysis_ids=[a.analysis_id], kind="counterfactual"))
        ref_an.append(a.analysis_id)
        ref_events.append(dp.event_id)

    perf: list[PlayerPerformance] = []
    scored = sorted(view.player_stats, key=lambda p: -(p.goals * 5 + p.key_passes * 2 + p.shots + p.interceptions
                                                      + p.tackles + p.passes_completed * 0.2 + p.modeled_shot_quality * 10))
    for p in scored[:4]:
        acc = f"{p.passes_completed}/{p.passes_attempted}"
        if L == "en":
            summ = (f"{p.name}: {acc} passes, {p.key_passes} key passes, {p.shots} shots, {p.goals} goals, "
                    f"{p.interceptions + p.tackles} ball wins.")
        else:
            summ = (f"{p.name}: {acc} passes, {p.key_passes} sleutelpasses, {p.shots} schoten, {p.goals} doelpunten, "
                    f"{p.interceptions + p.tackles} balveroveringen.")
        perf.append(PlayerPerformance(player_id=p.player_id, name=p.name, team_id=p.team_id, summary=summ,
                                      metrics={"passes_completed": p.passes_completed,
                                               "passes_attempted": p.passes_attempted, "key_passes": p.key_passes,
                                               "shots": p.shots, "goals": p.goals,
                                               "modeled_shot_quality": round(p.modeled_shot_quality, 3),
                                               "interceptions": p.interceptions, "tackles": p.tackles}))

    # Momentum: possession share and final-third actions per window.
    windows: list[MomentumWindow] = []
    dur = max(1, info.duration_ms)
    n_win = 5 if dur > 120_000 else 3
    step = dur / n_win
    home_dir = 1 if info.period == 1 else -1
    dirs = {home.team_id: home_dir, away.team_id: -home_dir}
    poss_events = [(e.sim_time_ms, e.team_id) for e in events
                   if e.event_type in (EventType.POSSESSION_CHANGED, EventType.RESTART) and e.team_id]
    first_team = next((e.team_id for e in events if e.event_type in (EventType.PASS_ATTEMPTED,
                       EventType.DRIBBLE_ATTEMPTED, EventType.SHOT_ATTEMPTED) and e.team_id), home.team_id)
    for w in range(n_win):
        t0, t1 = w * step, (w + 1) * step
        share = {home.team_id: 0.0, away.team_id: 0.0}
        cur = first_team
        last_t = 0.0
        for t, team in poss_events + [(dur, None)]:
            seg0, seg1 = max(last_t, t0), min(t, t1)
            if seg1 > seg0 and cur:
                share[cur] += seg1 - seg0
            if t >= t1:
                break
            last_t = t
            if team:
                cur = team
        tot = sum(share.values()) or 1
        ft = {home.team_id: 0, away.team_id: 0}
        for e in events:
            if t0 <= e.sim_time_ms < t1 and e.event_type in (EventType.PASS_ATTEMPTED, EventType.DRIBBLE_ATTEMPTED,
                                                            EventType.SHOT_ATTEMPTED) and e.team_id and e.x is not None:
                xa = e.x if dirs[e.team_id] == 1 else 105 - e.x
                if xa > 70:
                    ft[e.team_id] += 1
        windows.append(MomentumWindow(start_clock=format_clock(info.start_clock_ms + int(t0)),
                                      end_clock=format_clock(info.start_clock_ms + int(t1)),
                                      possession_share={k: round(v / tot, 3) for k, v in share.items()},
                                      final_third_entries=ft))

    ts = view.team_stats
    h, a_ = ts[home.team_id], ts[away.team_id]
    start, end = format_clock(info.start_clock_ms), format_clock(info.end_clock_ms)
    goals = [k for k in key if k.kind == "goal"]
    if L == "en":
        cas_head = f"{score_line}"
        story = [f"From {start} to {end}, {home.name} and {away.name} produced {h.shots + a_.shots} shots "
                 f"({h.shots} vs {a_.shots})."]
        story += [f"{k.match_clock}: {k.text}" for k in goals] or ["No goals in this segment."]
        if insights:
            story.append(f"OFFSCRIPT analysed {len(insights)} key decision(s): " + insights[0].text)
        if perf:
            story.append(f"Standout: {perf[0].summary}")
        ana_head = f"Analyst recap {start}-{end}: {score_line}"
        sections = [
            f"Passing: {home.short_name} {h.passes_completed}/{h.passes_attempted}"
            + (f" ({pct(h.pass_accuracy)})" if h.pass_accuracy is not None else "")
            + f", {away.short_name} {a_.passes_completed}/{a_.passes_attempted}"
            + (f" ({pct(a_.pass_accuracy)})" if a_.pass_accuracy is not None else "") + ".",
            f"Possession (observed synthetic timeline): {home.short_name} {pct(h.possession_share or 0)}, "
            f"{away.short_name} {pct(a_.possession_share or 0)}.",
            f"Modeled shot quality total (uncalibrated model estimate): {home.short_name} "
            f"{h.total_modeled_shot_quality:.2f}, {away.short_name} {a_.total_modeled_shot_quality:.2f}.",
            f"Ball wins: {home.short_name} {h.interceptions + h.tackles}, {away.short_name} {a_.interceptions + a_.tackles}.",
        ] + [f"Decision {i.match_clock}: {i.text}" for i in insights]
    else:
        cas_head = f"{score_line}"
        story = [f"Van {start} tot {end} kwamen {home.name} en {away.name} tot {h.shots + a_.shots} schoten "
                 f"({h.shots} tegen {a_.shots})."]
        story += [f"{k.match_clock}: {k.text}" for k in goals] or ["Geen doelpunten in dit fragment."]
        if insights:
            story.append(f"OFFSCRIPT analyseerde {len(insights)} sleutelbeslissing(en): " + insights[0].text)
        if perf:
            story.append(f"Uitblinker: {perf[0].summary}")
        ana_head = f"Analistenverslag {start}-{end}: {score_line}"
        sections = [
            f"Passing: {home.short_name} {h.passes_completed}/{h.passes_attempted}"
            + (f" ({pct(h.pass_accuracy, L)})" if h.pass_accuracy is not None else "")
            + f", {away.short_name} {a_.passes_completed}/{a_.passes_attempted}"
            + (f" ({pct(a_.pass_accuracy, L)})" if a_.pass_accuracy is not None else "") + ".",
            f"Balbezit (waargenomen synthetische tijdlijn): {home.short_name} {pct(h.possession_share or 0, L)}, "
            f"{away.short_name} {pct(a_.possession_share or 0, L)}.",
            f"Totale gemodelleerde schotkwaliteit (ongekalibreerde schatting): {home.short_name} "
            f"{h.total_modeled_shot_quality:.2f}, {away.short_name} {a_.total_modeled_shot_quality:.2f}.",
            f"Balveroveringen: {home.short_name} {h.interceptions + h.tackles}, {away.short_name} "
            f"{a_.interceptions + a_.tackles}.",
        ] + [f"Beslissing {i.match_clock}: {i.text}" for i in insights]
    return Recap(
        recap_id=new_id("recap"), match_id=info.match_id, language=L, generated_at=utcnow().isoformat(),
        generated_by="deterministic recap engine (narratives from verified analyses)",
        final_score=dict(fs), score_line=score_line, key_events=key, decision_insights=insights,
        player_performances=perf, momentum=windows, casual=RecapFormat(headline=cas_head, story=story),
        analyst=RecapFormat(headline=ana_head, story=sections), referenced_event_ids=sorted(set(ref_events)),
        referenced_analysis_ids=ref_an, disclaimer=DISCLAIMER[L])

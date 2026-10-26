"use client";

import type { Language, ViewerMode } from "@offscript/contracts";
import { activeFollow, decodeFollow, encodeFollow } from "@/lib/follow";
import { LANGUAGES, t, tr } from "@/lib/i18n";
import { actions, useApp } from "@/lib/store";
import BrandMark from "./BrandMark";
import ThemeToggle from "./ThemeToggle";

export function Logo() {
  return (
    <a href="/" className="flex items-center gap-2" aria-label="OFFSCRIPT home">
      <BrandMark size={30} id="hdr" />
      <span className="text-[15px] font-black tracking-[0.32em] text-white">OFFSCRIPT</span>
    </a>
  );
}

function Segmented<T extends string>(props: { label: string; value: T; options: { v: T; label: string }[]; onChange: (v: T) => void; testId?: string }) {
  return (
    <div role="radiogroup" aria-label={props.label} className="flex rounded-xl bg-white/[0.04] p-0.5" data-testid={props.testId}>
      {props.options.map((o) => (
        <button key={o.v} type="button" role="radio" aria-checked={props.value === o.v} onClick={() => props.onChange(o.v)} className="tab">
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Optional personalisation: follow a team or a player. "Everyone" (the default) changes nothing. */
function FollowPicker() {
  const s = useApp();
  const m = s.match;
  if (!m) return null;
  const en = s.lang !== "nl";
  const f = activeFollow(s.follow, m);
  const teams = [m.home, m.away];
  return (
    <label className={`flex items-center gap-1.5 rounded-xl border px-2 py-1 text-[12px] ${f ? "border-leaf-400/50 bg-leaf-500/10" : "border-white/[0.06] bg-white/[0.03]"}`}>
      <span className={f ? "font-semibold text-leaf-200" : "text-slate-400"}>{f ? "★" : ""} {tr(s.lang, { en: "Follow", nl: "Volg", es: "Seguir", fr: "Suivre", de: "Folgen" })}</span>
      <select value={encodeFollow(f)} onChange={(e) => actions.setFollow(decodeFollow(e.target.value))} data-testid="follow-select"
        aria-label={tr(s.lang, { en: "Follow a team or player", nl: "Volg een team of speler", es: "Sigue a un equipo o jugador", fr: "Suivre une équipe ou un joueur", de: "Einem Team oder Spieler folgen" })}
        className="max-w-36 truncate bg-transparent font-medium text-white outline-none">
        <option value="" className="bg-slate-900">{tr(s.lang, { en: "Everyone", nl: "Iedereen", es: "Todos", fr: "Tout le monde", de: "Alle" })}</option>
        <optgroup label={en ? "Teams" : "Teams"} className="bg-slate-900">
          {teams.map((t) => <option key={t.team_id} value={encodeFollow({ kind: "team", id: t.team_id })}>{t.name}</option>)}
        </optgroup>
        {teams.map((t) => (
          <optgroup key={t.team_id} label={t.short_name} className="bg-slate-900">
            {m.players.filter((p) => p.team_id === t.team_id).sort((a, b) => a.shirt_number - b.shirt_number).map((p) => (
              <option key={p.player_id} value={encodeFollow({ kind: "player", id: p.player_id })}>{p.shirt_number} · {p.name}</option>
            ))}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

export default function Header() {
  const s = useApp();
  const L = t(s.lang);
  const live = s.health?.agent_mode === "foundry";
  const connColor = s.conn === "open" ? "bg-emerald-400" : s.conn === "connecting" ? "bg-amber-400" : "bg-slate-500";
  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.05] bg-ink/75 backdrop-blur-xl">
      <span aria-hidden className="pointer-events-none absolute inset-x-0 -bottom-px h-px bg-gradient-to-r from-transparent via-leaf-400/50 to-transparent" />
      <div className="app-header-primary">
        <div className="app-header-logo">
        <Logo />
        </div>
        <nav role="tablist" aria-label="View" className="flex rounded-xl bg-white/[0.04] p-0.5" data-testid="view-tabs">
          {(["live", "multiverse"] as const).map((v) => (
            <button key={v} type="button" role="tab" aria-selected={s.appView === v} onClick={() => actions.setView(v)}
              data-testid={`tab-${v}`}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-bold transition ${s.appView === v
                ? v === "multiverse" ? "bg-gradient-to-r from-leaf-600 to-sage-600 text-white shadow-lg shadow-sage-900/40" : "bg-white text-slate-900"
                : "text-slate-400 hover:text-white"}`}>
              {v === "live" ? tr(s.lang, { en: "Live match", nl: "Live wedstrijd", es: "Partido en directo", fr: "Match en direct", de: "Live-Spiel" }) : "Multiverse"}
            </button>
          ))}
        </nav>
        <div className="app-header-settings">
          <label className="flex items-center rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-1 text-[12px]">
            <span className="sr-only">{L.language}</span>
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mr-1 h-4 w-4 shrink-0 text-slate-400">
              <circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" /><path d="M3 12h18" />
            </svg>
            <select value={s.lang} onChange={(e) => actions.setLang(e.target.value as Language)} data-testid="lang-select"
              aria-label={L.language} className="w-12 bg-transparent font-semibold text-white outline-none">
              {LANGUAGES.map((l) => <option key={l.v} value={l.v} className="bg-slate-900">{l.short}</option>)}
            </select>
          </label>
          <ThemeToggle lang={s.lang} />
        </div>
      </div>
      <div className="app-header-secondary flex flex-wrap items-center gap-x-4 gap-y-2 px-4 pb-2.5">
        {s.scenarios.length > 0 && <label className="flex min-w-0 items-center gap-2">
          <span className="sr-only">{L.scenario}</span>
          <select value={s.scenarioId ?? ""} onChange={(e) => void actions.selectScenario(e.target.value)} data-testid="scenario-select"
            className="max-w-60 truncate rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-1.5 text-[13px] font-medium text-white outline-none hover:bg-white/[0.06]">
            {s.scenarios.map((sc) => (
              <option key={sc.scenario_id} value={sc.scenario_id} className="bg-slate-900">{sc.title}</option>
            ))}
          </select>
        </label>}
        {s.appView === "live" && <FollowPicker />}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Segmented<ViewerMode> label={L.mode} value={s.mode} onChange={actions.setMode} testId="mode-switch"
            options={[{ v: "casual", label: L.casual }, { v: "analyst", label: L.analyst }, { v: "broadcaster", label: L.broadcaster }]} />
          <button type="button" onClick={() => void actions.openRecap()} data-testid="open-recap" className="btn">{L.recap}</button>
          <div className="flex items-center gap-2 rounded-xl bg-white/[0.04] px-2.5 py-1.5 text-[11px]">
            <span className={`rounded-md px-1.5 py-0.5 font-semibold ${live ? "bg-leaf-500/20 text-leaf-200" : "text-slate-300"}`}
              title={live ? `Microsoft Foundry deployment: ${s.health?.foundry_deployment}` : "No Foundry deployment configured: agents use the labelled deterministic planner"}
              data-testid="agent-mode">
              {L.agentMode}: {live ? `${L.foundryLive} · ${s.health?.foundry_deployment}` : L.policy}
            </span>
            <span className="h-3 w-px bg-white/10" />
            <span className="flex items-center gap-1.5 text-slate-400" aria-live="polite">
              <span className={`h-1.5 w-1.5 rounded-full ${connColor} ${s.conn === "open" ? "shadow-[0_0_8px] shadow-emerald-400" : ""}`} />
              {s.conn === "open" ? L.live : s.conn === "connecting" ? L.connecting : L.offline}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}

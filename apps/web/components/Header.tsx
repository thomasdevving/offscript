"use client";

import type { Language, ViewerMode } from "@parallel/contracts";
import { t } from "@/lib/i18n";
import { actions, useApp } from "@/lib/store";

export function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
        <rect x="1" y="1" width="30" height="30" rx="8" fill="#0b1220" stroke="#334155" />
        <path d="M9 23 L9 9" stroke="#f8fafc" strokeWidth="2.6" strokeLinecap="round" />
        <path d="M16 23 L16 9" stroke="#60a5fa" strokeWidth="2.6" strokeLinecap="round" />
        <path d="M23 23 L23 9" stroke="#a78bfa" strokeWidth="2.6" strokeLinecap="round" strokeDasharray="2.5 2.2" />
      </svg>
      <div className="leading-tight">
        <div className="text-lg font-black tracking-[0.28em] text-white">PARALLEL</div>
      </div>
    </div>
  );
}

function Segmented<T extends string>(props: { label: string; value: T; options: { v: T; label: string }[]; onChange: (v: T) => void; testId?: string }) {
  return (
    <div role="radiogroup" aria-label={props.label} className="flex rounded-lg bg-slate-900 p-0.5" data-testid={props.testId}>
      {props.options.map((o) => (
        <button key={o.v} type="button" role="radio" aria-checked={props.value === o.v} onClick={() => props.onChange(o.v)}
          className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${props.value === o.v ? "bg-slate-200 text-slate-900" : "text-slate-300 hover:text-white"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function Header() {
  const s = useApp();
  const L = t(s.lang);
  const live = s.health?.agent_mode === "foundry";
  const connColor = s.conn === "open" ? "bg-emerald-400" : s.conn === "connecting" ? "bg-amber-400" : "bg-red-400";
  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line bg-ink/90 px-4 py-2.5 backdrop-blur">
      <Logo />
      <span className="hidden text-xs text-slate-400 lg:inline">{L.tagline}</span>
      <label className="flex items-center gap-2 text-xs text-slate-400">
        <span className="sr-only md:not-sr-only">{L.scenario}</span>
        <select value={s.scenarioId ?? ""} onChange={(e) => void actions.selectScenario(e.target.value)} data-testid="scenario-select"
          className="max-w-64 rounded-md border border-line bg-slate-900 px-2 py-1.5 text-sm text-white">
          {s.scenarios.map((sc) => (
            <option key={sc.scenario_id} value={sc.scenario_id}>{sc.title}</option>
          ))}
        </select>
      </label>
      <div className="ml-auto flex flex-wrap items-center gap-3">
        <Segmented<ViewerMode> label={L.mode} value={s.mode} onChange={actions.setMode} testId="mode-switch"
          options={[{ v: "casual", label: L.casual }, { v: "analyst", label: L.analyst }, { v: "broadcaster", label: L.broadcaster }]} />
        <Segmented<Language> label={L.language} value={s.lang} onChange={actions.setLang} testId="lang-switch"
          options={[{ v: "en", label: "EN" }, { v: "nl", label: "NL" }]} />
        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${live ? "border-blue-400/50 bg-blue-500/10 text-blue-200" : "border-slate-600 bg-slate-800 text-slate-300"}`}
          title={live ? `Microsoft Foundry deployment: ${s.health?.foundry_deployment}` : "No Foundry deployment configured: agents use the labelled deterministic planner"}
          data-testid="agent-mode">
          {L.agentMode}: {live ? `${L.foundryLive} · ${s.health?.foundry_deployment}` : L.policy}
        </span>
        <button type="button" onClick={() => void actions.openRecap()} data-testid="open-recap"
          className="rounded-md bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-100 hover:bg-slate-700">{L.recap}</button>
        <span className="flex items-center gap-1.5 text-xs text-slate-400" aria-live="polite">
          <span className={`h-2 w-2 rounded-full ${connColor}`} />
          {s.conn === "open" ? L.live : s.conn === "connecting" ? L.connecting : L.offline}
        </span>
      </div>
    </header>
  );
}

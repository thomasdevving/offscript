"use client";

import type { Language, ViewerMode } from "@parallel/contracts";
import { t } from "@/lib/i18n";
import { actions, useApp } from "@/lib/store";
import BrandMark from "./BrandMark";
import ThemeToggle from "./ThemeToggle";

export function Logo() {
  return (
    <a href="/" className="flex items-center gap-2" aria-label="PARALLEL home">
      <BrandMark size={30} id="hdr" />
      <span className="text-[15px] font-black tracking-[0.32em] text-white">PARALLEL</span>
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

export default function Header() {
  const s = useApp();
  const L = t(s.lang);
  const live = s.health?.agent_mode === "foundry";
  const connColor = s.conn === "open" ? "bg-emerald-400" : s.conn === "connecting" ? "bg-amber-400" : "bg-slate-500";
  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.05] bg-ink/75 backdrop-blur-xl">
      <span aria-hidden className="pointer-events-none absolute inset-x-0 -bottom-px h-px bg-gradient-to-r from-transparent via-leaf-400/50 to-transparent" />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
        <Logo />
        <nav role="tablist" aria-label="View" className="flex rounded-xl bg-white/[0.04] p-0.5" data-testid="view-tabs">
          {(["live", "multiverse"] as const).map((v) => (
            <button key={v} type="button" role="tab" aria-selected={s.appView === v} onClick={() => actions.setView(v)}
              data-testid={`tab-${v}`}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-bold transition ${s.appView === v
                ? v === "multiverse" ? "bg-gradient-to-r from-leaf-600 to-sage-600 text-white shadow-lg shadow-sage-900/40" : "bg-white text-slate-900"
                : "text-slate-400 hover:text-white"}`}>
              {v === "live" ? (s.lang === "en" ? "Live match" : "Live wedstrijd") : "Multiverse"}
            </button>
          ))}
        </nav>
        {s.scenarios.length > 0 && <label className="flex min-w-0 items-center gap-2">
          <span className="sr-only">{L.scenario}</span>
          <select value={s.scenarioId ?? ""} onChange={(e) => void actions.selectScenario(e.target.value)} data-testid="scenario-select"
            className="max-w-72 truncate rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-1.5 text-[13px] font-medium text-white outline-none hover:bg-white/[0.06]">
            {s.scenarios.map((sc) => (
              <option key={sc.scenario_id} value={sc.scenario_id} className="bg-slate-900">{sc.title}</option>
            ))}
          </select>
        </label>}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Segmented<ViewerMode> label={L.mode} value={s.mode} onChange={actions.setMode} testId="mode-switch"
            options={[{ v: "casual", label: L.casual }, { v: "analyst", label: L.analyst }, { v: "broadcaster", label: L.broadcaster }]} />
          <Segmented<Language> label={L.language} value={s.lang} onChange={actions.setLang} testId="lang-switch"
            options={[{ v: "en", label: "EN" }, { v: "nl", label: "NL" }]} />
          <button type="button" onClick={() => void actions.openRecap()} data-testid="open-recap" className="btn">{L.recap}</button>
          <ThemeToggle lang={s.lang} />
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

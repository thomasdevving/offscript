"use client";

import { useEffect } from "react";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n";
import { actions, useApp } from "@/lib/store";
import AnalysisPanel from "./AnalysisPanel";
import Header from "./Header";
import { DecisionList, EventFeed, Scoreboard, StatsPanel } from "./MatchIntel";
import PitchStage from "./PitchStage";
import PlaybackControls, { WhatIfControls } from "./PlaybackControls";
import RecapDrawer from "./RecapDrawer";

function useKeyboard() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.key === " ") {
        e.preventDefault();
        actions.togglePlay();
      } else if (e.key === "ArrowRight") actions.jumpDecision(1);
      else if (e.key === "ArrowLeft") actions.jumpDecision(-1);
      else if (e.key === "1") actions.setMode("casual");
      else if (e.key === "2") actions.setMode("analyst");
      else if (e.key === "3") actions.setMode("broadcaster");
      else if (e.key === "Escape") actions.backToMatch();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

/** Keeps the observed statistics fresh while the stream plays (deterministic state replay endpoint). */
function useLiveStats() {
  useEffect(() => {
    const id = setInterval(async () => {
      const s = useApp.getState();
      if (!s.matchId || !s.playback.playing) return;
      try {
        const v = await api.state(s.matchId, s.playback.serverT);
        if (useApp.getState().matchId === s.matchId) useApp.setState({ stats: v });
      } catch {
        /* transient */
      }
    }, 1500);
    return () => clearInterval(id);
  }, []);
}

export default function Dashboard() {
  const lang = useApp((s) => s.lang);
  const healthError = useApp((s) => s.healthError);
  const scenario = useApp((s) => s.scenarios.find((x) => x.scenario_id === s.scenarioId));
  const L = t(lang);
  useEffect(() => {
    void actions.init();
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  useKeyboard();
  useLiveStats();

  return (
    <div className="flex min-h-screen flex-col overflow-x-hidden">
      <a href="#pitch" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-1 focus:text-black">
        Skip to pitch
      </a>
      <Header />
      {healthError && (
        <div className="bg-red-500/15 px-4 py-2 text-sm text-red-200" role="alert">
          API unreachable ({healthError}). Retrying… Start the backend with <code>uvicorn app.main:app</code>.
        </div>
      )}
      <main className="grid flex-1 gap-3 p-3 xl:grid-cols-[300px_minmax(0,1fr)_430px]">
        <aside className="order-3 flex min-w-0 flex-col gap-3 xl:order-1" aria-label={L.stats}>
          <Scoreboard />
          <DecisionList />
          <EventFeed />
          <StatsPanel />
        </aside>
        <section id="pitch" className="order-1 flex min-w-0 flex-col gap-3 xl:order-2" aria-label="Pitch">
          {scenario && (
            <div className="flex flex-wrap items-baseline gap-x-3 px-1">
              <h1 className="text-xl font-black text-white">{scenario.title}</h1>
              <p className="text-sm text-slate-400">{scenario.description}</p>
            </div>
          )}
          <div className="overflow-hidden rounded-2xl border border-line bg-panel p-2 shadow-2xl shadow-blue-950/40">
            <PitchStage />
          </div>
          <WhatIfControls />
          <PlaybackControls />
          <p className="px-1 text-[11px] text-slate-500">
            {lang === "en"
              ? "Synthetic match with fictional teams and players. Alternatives are simulated by an explicit, uncalibrated model; they are estimates, not what would have happened."
              : "Synthetische wedstrijd met fictieve teams en spelers. Alternatieven worden gesimuleerd met een expliciet, ongekalibreerd model; het zijn schattingen, geen werkelijkheid."}
          </p>
        </section>
        <aside className="order-2 min-w-0 xl:order-3" aria-label={L.parallelAnalysis}>
          <AnalysisPanel />
        </aside>
      </main>
      <RecapDrawer />
    </div>
  );
}

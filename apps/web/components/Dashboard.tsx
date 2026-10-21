"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n";
import { actions, useApp } from "@/lib/store";
import AnalysisPanel from "./AnalysisPanel";
import BrandMark from "./BrandMark";
import Header from "./Header";
import { MatchCentre, Moments } from "./MatchIntel";
import PitchStage from "./PitchStage";
import PlaybackControls, { WhatIfControls } from "./PlaybackControls";
import RecapDrawer from "./RecapDrawer";
import MultiverseView from "./multiverse/MultiverseView";

function useKeyboard() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (useApp.getState().appView !== "live") return;
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

/** Shown while the API is cold-starting (or unreachable): the static UI is up before the engine is. */
function WarmingUp({ error }: { error: string | null }) {
  const lang = useApp((s) => s.lang);
  const L = t(lang);
  return (
    <div className="flex flex-1 items-center justify-center p-6" role="status" aria-live="polite" data-testid="warming-up">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-6 w-fit animate-pulse"><BrandMark size={96} id="warm" /></div>
        <h1 className="text-xl font-black text-white">{L.warmingTitle}</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-400">{L.warmingBody}</p>
        {error && <p className="mt-4 font-mono text-[11px] text-slate-600">{error} · retrying every 3 s</p>}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const lang = useApp((s) => s.lang);
  const healthError = useApp((s) => s.healthError);
  const ready = useApp((s) => s.scenarios.length > 0);
  const scenario = useApp((s) => s.scenarios.find((x) => x.scenario_id === s.scenarioId));
  const appView = useApp((s) => s.appView);
  const L = t(lang);
  // A scaled-to-zero API holds the first request while it starts: after a short wait, explain why.
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    void actions.init();
    actions.restorePitchDim();
    // Deep links from the landing page open in a viewer mode (?mode=casual|analyst|broadcaster).
    const m = new URLSearchParams(window.location.search).get("mode");
    if (m === "casual" || m === "analyst" || m === "broadcaster") actions.setMode(m);
    const id = setTimeout(() => setSlow(true), 2500);
    return () => clearTimeout(id);
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
      {healthError && ready && (
        <div className="bg-amber-500/10 px-4 py-1.5 text-center text-xs text-amber-200" role="alert">
          {lang === "en" ? "Connection to the analysis service lost. Reconnecting…" : "Verbinding met de analysedienst verbroken. Opnieuw verbinden…"}
        </div>
      )}
      {!ready && (healthError || slow) ? <WarmingUp error={healthError} /> : appView === "multiverse" ? <MultiverseView /> : (
        <main className="mx-auto grid w-full max-w-[1760px] flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_400px] 2xl:grid-cols-[minmax(0,1fr)_440px]">
          <section id="pitch" className="flex min-w-0 flex-col gap-3" aria-label="Pitch">
            {scenario && (
              <div className="px-1">
                <h1 className="text-2xl font-black tracking-tight text-white">{scenario.title}</h1>
                <p className="mt-1 max-w-3xl text-sm leading-relaxed text-slate-400">{scenario.description}</p>
              </div>
            )}
            <div className="mx-auto w-full max-w-[max(560px,calc((100vh-300px)*1.5))] frame overflow-hidden p-2 shadow-2xl shadow-black/60">
              <PitchStage />
            </div>
            <WhatIfControls />
            <PlaybackControls />
            <Moments />
            <MatchCentre />
            <p className="px-1 text-[11px] text-slate-600">
              {lang === "en"
                ? "Synthetic match with fictional teams and players. Alternatives are simulated by an explicit, uncalibrated model; they are estimates, not what would have happened."
                : "Synthetische wedstrijd met fictieve teams en spelers. Alternatieven worden gesimuleerd met een expliciet, ongekalibreerd model; het zijn schattingen, geen werkelijkheid."}
            </p>
          </section>
          <aside className="min-w-0 lg:sticky lg:top-[62px] lg:max-h-[calc(100vh-78px)] lg:overflow-y-auto lg:pr-1" aria-label={L.analysisTitle}>
            <AnalysisPanel />
          </aside>
        </main>
      )}
      <RecapDrawer />
    </div>
  );
}

"use client";

import { Space_Grotesk, Unbounded } from "next/font/google";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import BrandMark from "../BrandMark";

type Lang = "en" | "nl";

// Landing-only type: a wide geometric display face for headlines, a grotesk for body copy.
const display = Unbounded({ subsets: ["latin"], variable: "--font-display", display: "swap" });
const body = Space_Grotesk({ subsets: ["latin"], variable: "--font-body", display: "swap" });

const APP = "/app/?scenario=shoot_vs_pass";
const LINKS = {
  multiverse: `${APP}&view=multiverse`,
  demo: `${APP}&dim=3d`,
  fans: `${APP}&mode=casual`,
  analysts: `${APP}&mode=analyst`,
  broadcast: `${APP}&mode=broadcaster`,
};

/*
 * Everything drawn on this page is the 73' demo scenario (demo-match-073, decision at 72:47):
 * real player positions from its frozen snapshot and the figures the simulation model reports for it.
 */
type Pt = [number, number];
const HOME: [string, number, number, number][] = [
  ["H01", 82.5, 34, 1], ["H02", 32.4, 9.4, 2], ["H04", 54.3, 47, 4], ["H05", 54.2, 27.8, 5], ["H03", 37.9, 66, 3], ["H06", 38, 32.4, 6],
  ["H08", 30.1, 31.2, 8], ["H10", 22.8, 37, 10], ["H07", 11.8, 20.5, 7], ["H11", 13.9, 62.4, 11], ["H09", 12.2, 32, 9],
];
const AWAY: [string, number, number, number][] = [
  ["A01", 3.2, 34.4, 1], ["A02", 13.8, 57.7, 2], ["A04", 11.4, 34.4, 4], ["A05", 12.4, 37.6, 5], ["A03", 11.5, 30.4, 3], ["A06", 21.6, 37.2, 6],
  ["A08", 20.3, 38, 8], ["A10", 32.6, 27.1, 10], ["A07", 28.6, 58.5, 7], ["A11", 34.7, 12.9, 11], ["A09", 39.7, 35.6, 9],
];

type OptionId = "shot" | "pass" | "switch";
const OPTION_IDS: OptionId[] = ["shot", "pass", "switch"];
const OPTIONS: Record<OptionId, { d: string; end: Pt; goal: string; target?: string }> = {
  shot: { d: "M 22.8 37 L 13.5 36.2", end: [13.5, 36.2], goal: "0.0%" },
  pass: { d: "M 22.8 37 Q 21 25 11.8 20.5 Q 5 25 1 33", end: [11.8, 20.5], goal: "2.0%", target: "H07" },
  switch: { d: "M 22.8 37 Q 22 54 13.9 62.4", end: [13.9, 62.4], goal: "0.0%", target: "H11" },
};

const COPY = {
  en: {
    nav: [["#how", "How it works"], ["#agents", "Agents"], ["#compare", "Compare"], ["#perspectives", "Use cases"]],
    open: "Open app",
    eyebrow: "Counterfactual football intelligence",
    title: ["Every decision", "creates another game."],
    sub: "PARALLEL freezes the moment a player decides, plays every option forward hundreds of times and lets a team of AI agents explain which future was more promising, with the evidence on the table.",
    explore: "Explore the Multiverse",
    demo: "Watch demo",
    stats: [["200", "simulations per option"], ["5", "agents, one verified answer"], ["3", "viewer modes (fan, analyst, broadcaster)"]],
    choose: "Choose a different action",
    options: { shot: "Shot", pass: "Pass", switch: "Switch" } as Record<OptionId, string>,
    optionLabel: { shot: "Shoot · actual", pass: "Pass to Mbeki-Larsen", switch: "Pass to Kestrel" } as Record<OptionId, string>,
    cards: { shot: "Actual", pass: "Alternative 1", switch: "Alternative 2" } as Record<OptionId, string>,
    howEyebrow: "How it works",
    howTitle: ["From one moment", "to many possibilities."],
    howSub: "You choose a decision, the agents compete with strategies, the simulator explores the outcomes, and you rewind, compare and discover what could have happened.",
    steps: [
      ["Choose", "Change the decision, or let the agents suggest the alternatives."],
      ["Simulate", "Attacking and defending agents plan against each other; every option runs hundreds of times."],
      ["Explore", "Compare outcomes, read the tactical explanation and continue to the next decision."],
    ],
    agentsEyebrow: "Multi-agent intelligence",
    agentsTitle: ["Attacking ideas.", "Defensive answers."],
    agentsSub: "Specialised agents read the game from different perspectives, propose strategies and react to each other. Every action is validated by a deterministic football simulator.",
    agents: [
      ["Attacking agent", "Finds promising passes, runs and shots to maximise attacking value."],
      ["Defending agent", "Chooses a realistic defensive response to reduce the threat."],
      ["Simulation agent", "Runs Monte Carlo simulations for every action and response."],
      ["Verification agent", "Checks that every claim is grounded in the numbers."],
      ["Explanation agent", "Turns the outcome into a clear, evidence-based story."],
    ],
    battle: "Agent battle",
    battleAt: "72:47 decision",
    attack: ["Attacking agent", "Proposes a pass to Mbeki-Larsen"],
    defend: ["Defending agent", "Answers by covering the passing lane"],
    result: "Simulation result",
    metrics: [["1.0%", "chance of goal vs this defence", 0.1], ["75%", "pass completion", 0.75], ["28%", "turnover risk", 0.28]] as [string, string, number][],
    insightTitle: "Tactical insight",
    insight: "Covering the lane lowers the pass's modelled goal chance from 1.4% to 1.0%. In the continuation shown, the pass still reaches Mbeki-Larsen.",
    compareEyebrow: "Compare realities",
    compareTitle: ["See how the game", "could have unfolded."],
    compareSub: "Watch the actual outcome and your alternative side by side. Different decisions. Different strategies. Different futures.",
    actualMatch: "Actual match",
    yourAlt: "Your alternative",
    actualCaption: "72:49 · Shot blocked",
    altCaption: "72:49 · Pass completed",
    play: "Play",
    perspEyebrow: "Built for different perspectives",
    perspTitle: "Same data. Different stories.",
    persp: [
      ["Fans", "Relive the action and explore what could have happened."],
      ["Analysts", "Dive into probabilities, passing lanes and tactical patterns."],
      ["Broadcasters", "Clear storylines and broadcast-ready captions."],
    ],
    finalEyebrow: "The football multiverse",
    finalTitle: ["Same moment.", "Infinite games."],
    finalSub: "Step into the Multiverse and explore alternative futures with AI agents, simulation and real tactical reasoning.",
    note: "Synthetic matches with fictional teams and players. Figures shown come from the 73' demo scenario under an explicit, uncalibrated simulation model: estimates, not what would have happened.",
  },
  nl: {
    nav: [["#how", "Hoe het werkt"], ["#agents", "Agents"], ["#compare", "Vergelijken"], ["#perspectives", "Toepassingen"]],
    open: "Open app",
    eyebrow: "Contrafactische voetbalintelligentie",
    title: ["Elke beslissing", "creëert een andere wedstrijd."],
    sub: "PARALLEL bevriest het moment waarop een speler beslist, speelt elke optie honderden keren vooruit en laat een team van AI-agents uitleggen welke toekomst kansrijker was, met het bewijs op tafel.",
    explore: "Betreed het Multiverse",
    demo: "Bekijk de demo",
    stats: [["200", "simulaties per optie"], ["5", "agents, één geverifieerd antwoord"], ["3", "kijkmodi (fan, analist, omroep)"]],
    choose: "Kies een andere actie",
    options: { shot: "Schot", pass: "Pass", switch: "Wissel" } as Record<OptionId, string>,
    optionLabel: { shot: "Schot · echt", pass: "Pass naar Mbeki-Larsen", switch: "Pass naar Kestrel" } as Record<OptionId, string>,
    cards: { shot: "Echt", pass: "Alternatief 1", switch: "Alternatief 2" } as Record<OptionId, string>,
    howEyebrow: "Hoe het werkt",
    howTitle: ["Van één moment", "naar talloze mogelijkheden."],
    howSub: "Jij kiest een beslissing, de agents strijden met strategieën, de simulator verkent de uitkomsten en jij spoelt terug, vergelijkt en ontdekt wat er had kunnen gebeuren.",
    steps: [
      ["Kiezen", "Verander de beslissing, of laat de agents de alternatieven voorstellen."],
      ["Simuleren", "Aanvallende en verdedigende agents plannen tegen elkaar; elke optie wordt honderden keren gespeeld."],
      ["Verkennen", "Vergelijk uitkomsten, lees de tactische uitleg en ga door naar de volgende beslissing."],
    ],
    agentsEyebrow: "Multi-agent intelligentie",
    agentsTitle: ["Aanvallende ideeën.", "Verdedigende antwoorden."],
    agentsSub: "Gespecialiseerde agents lezen het spel vanuit verschillende perspectieven, stellen strategieën voor en reageren op elkaar. Elke actie wordt gevalideerd door een deterministische voetbalsimulator.",
    agents: [
      ["Aanvallende agent", "Zoekt kansrijke passes, loopacties en schoten voor maximale aanvalswaarde."],
      ["Verdedigende agent", "Kiest een realistische verdedigende reactie om het gevaar te beperken."],
      ["Simulatie-agent", "Draait Monte Carlo-simulaties voor elke actie en reactie."],
      ["Verificatie-agent", "Controleert dat elke bewering op de cijfers steunt."],
      ["Uitleg-agent", "Maakt van de uitkomst een helder verhaal, onderbouwd met bewijs."],
    ],
    battle: "Agentduel",
    battleAt: "beslissing 72:47",
    attack: ["Aanvallende agent", "Stelt een pass naar Mbeki-Larsen voor"],
    defend: ["Verdedigende agent", "Antwoordt door de passlijn af te dekken"],
    result: "Simulatieresultaat",
    metrics: [["1,0%", "kans op een doelpunt tegen deze verdediging", 0.1], ["75%", "geslaagde passes", 0.75], ["28%", "kans op balverlies", 0.28]] as [string, string, number][],
    insightTitle: "Tactisch inzicht",
    insight: "Het afdekken van de lijn verlaagt de gemodelleerde doelkans van de pass van 1,4% naar 1,0%. In het getoonde vervolg komt de pass toch aan bij Mbeki-Larsen.",
    compareEyebrow: "Vergelijk werkelijkheden",
    compareTitle: ["Zie hoe de wedstrijd", "had kunnen verlopen."],
    compareSub: "Bekijk de echte uitkomst en jouw alternatief naast elkaar. Andere beslissingen. Andere strategieën. Andere toekomsten.",
    actualMatch: "Echte wedstrijd",
    yourAlt: "Jouw alternatief",
    actualCaption: "72:49 · Schot geblokt",
    altCaption: "72:49 · Pass aangekomen",
    play: "Afspelen",
    perspEyebrow: "Gemaakt voor verschillende perspectieven",
    perspTitle: "Dezelfde data. Andere verhalen.",
    persp: [
      ["Fans", "Beleef de actie opnieuw en ontdek wat er had kunnen gebeuren."],
      ["Analisten", "Duik in kansen, passlijnen en tactische patronen."],
      ["Omroepen", "Heldere verhaallijnen en ondertitels klaar voor uitzending."],
    ],
    finalEyebrow: "Het voetbalmultiverse",
    finalTitle: ["Hetzelfde moment.", "Oneindig veel wedstrijden."],
    finalSub: "Stap in het Multiverse en verken alternatieve toekomsten met AI-agents, simulatie en echte tactische redenering.",
    note: "Synthetische wedstrijden met fictieve teams en spelers. De getoonde cijfers komen uit het 73'-demoscenario onder een expliciet, ongekalibreerd simulatiemodel: schattingen, geen werkelijkheid.",
  },
} as const;
type Copy = (typeof COPY)[Lang];

/* ------------------------------------------------------------------------------------------------ */

function Markings({ stroke = "rgba(238,246,234,0.7)", w = 0.3 }: { stroke?: string; w?: number }) {
  return (
    <g fill="none" stroke={stroke} strokeWidth={w}>
      <rect x={0} y={0} width={105} height={68} />
      <line x1={52.5} y1={0} x2={52.5} y2={68} />
      <circle cx={52.5} cy={34} r={9.15} />
      <rect x={0} y={13.85} width={16.5} height={40.3} />
      <rect x={88.5} y={13.85} width={16.5} height={40.3} />
      <rect x={0} y={24.85} width={5.5} height={18.3} />
      <rect x={99.5} y={24.85} width={5.5} height={18.3} />
    </g>
  );
}

/** Flat pitch thumbnail with the real positions and one highlighted path. */
function MiniPitch({ path, tone = "#8fca7c", dashed, crop, view, players = true, extra, animKey, dot = 1.3 }: {
  path?: string; tone?: string; dashed?: boolean; crop?: boolean; view?: string; players?: boolean; extra?: React.ReactNode; animKey?: number; dot?: number;
}) {
  return (
    <svg viewBox={view ?? (crop ? "-1 8 64 48" : "-2 -2 109 72")} className="block h-auto w-full" aria-hidden>
      <rect x={-2} y={-2} width={109} height={72} fill="#0f3a26" />
      {[0, 2, 4, 6, 8].map((i) => <rect key={i} x={i * 10.5} y={0} width={10.5} height={68} fill="#134330" />)}
      <Markings stroke="rgba(238,246,234,0.45)" w={0.35} />
      {players && HOME.map(([id, x, y]) => <circle key={id} cx={x} cy={y} r={dot} fill="#38bdf8" />)}
      {players && AWAY.map(([id, x, y]) => <circle key={id} cx={x} cy={y} r={dot} fill="#f59e0b" />)}
      {path && (
        <path key={animKey} d={path} fill="none" stroke={tone} strokeWidth={0.8} strokeLinecap="round" pathLength={100}
          strokeDasharray={dashed ? "1.6 1.2" : undefined} className={dashed ? "" : "draw-path"} style={{ filter: `drop-shadow(0 0 1px ${tone})` }} />
      )}
      {extra}
    </svg>
  );
}

const pos = (x: number, y: number) => ({ left: `${(x / 105) * 100}%`, top: `${(y / 68) * 100}%` });

function Pin({ x, y, n, team, ring }: { x: number; y: number; n: number; team: "home" | "away"; ring?: string }) {
  return (
    <div className="pin" style={pos(x, y)}>
      {ring && <span className="pin-ring" style={{ borderColor: ring, boxShadow: `0 0 12px ${ring}` }} />}
      <span className="pin-shadow" />
      <span className="billboard pin-body">
        <span className={`pin-head ${team === "home" ? "bg-sky-400 text-sky-950" : "bg-amber-400 text-amber-950"}`}>{n}</span>
        <span className="pin-stem" />
      </span>
    </div>
  );
}

const STROKE = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" } as const;

function OptionIcon({ id }: { id: OptionId }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      {id === "shot" && <><circle cx={12} cy={12} r={8} {...STROKE} /><circle cx={12} cy={12} r={3.5} {...STROKE} /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" {...STROKE} /></>}
      {id === "pass" && <><circle cx={5} cy={18} r={2} {...STROKE} /><circle cx={19} cy={6} r={2} {...STROKE} /><path d="M7 16 Q 9 6 17 6.5" {...STROKE} strokeDasharray="2 2" /></>}
      {id === "switch" && <path d="M4 8h13l-3-3M20 16H7l3 3" {...STROKE} />}
    </svg>
  );
}

/** Hero: the frozen 73' pitch as a tilted slab; pick an option and its path lights up. */
function HeroScene({ C, sel, setSel }: { C: Copy; sel: OptionId; setSel: (o: OptionId) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      el.style.setProperty("--rx", `${(((e.clientX - r.left) / r.width - 0.5) * 10).toFixed(2)}deg`);
      el.style.setProperty("--ry", `${(-((e.clientY - r.top) / r.height - 0.5) * 6).toFixed(2)}deg`);
    };
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, []);
  const opt = OPTIONS[sel];
  const tone = sel === "shot" ? "#f8fafc" : "#d4ee8f";
  return (
    <div className="relative grid gap-4 xl:grid-cols-[minmax(0,1fr)_150px]">
      <div ref={ref} className="scene hero-scene">
        <div className="stage">
          <div className="layer base">
            <svg viewBox="-1 -1 107 70" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
              <Markings />
              <path key={sel} d={opt.d} fill="none" stroke={tone} strokeWidth={0.7} strokeLinecap="round" pathLength={100}
                className={sel === "shot" ? "" : "draw-path"} strokeDasharray={sel === "shot" ? "1.5 1" : undefined}
                style={{ filter: `drop-shadow(0 0 1.4px ${tone})` }} />
              {sel === "shot" && <path d="M 12.6 35.4 l 1.8 1.8 M 14.4 35.4 l -1.8 1.8" stroke="#f97316" strokeWidth={0.5} />}
            </svg>
            {HOME.map(([id, x, y, n]) => <Pin key={id} x={x} y={y} n={n} team="home"
              ring={id === "H10" ? "#facc15" : id === opt.target ? "#d4ee8f" : undefined} />)}
            {AWAY.map(([id, x, y, n]) => <Pin key={id} x={x} y={y} n={n} team="away" />)}
            <div className="anchor3d" style={pos(opt.end[0] + 2, opt.end[1] - 4)}>
              <span className="billboard tag3d" style={{ borderColor: tone, color: tone }}>{C.optionLabel[sel]} · {opt.goal}</span>
            </div>
          </div>
        </div>
        {/* The action picker floats above the pitch like a coach's tablet. */}
        <div className="chooser glass absolute left-[4%] top-[2%] z-10 p-2.5 sm:left-[8%]">
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">{C.choose}</div>
          <div role="radiogroup" aria-label={C.choose} className="flex gap-1.5">
            {OPTION_IDS.map((o) => (
              <button key={o} type="button" role="radio" aria-checked={sel === o} onClick={() => setSel(o)}
                className={`flex w-[62px] flex-col items-center gap-1 py-2 text-[10.5px] font-semibold transition ${sel === o
                  ? "bg-leaf-500/20 text-leaf-100 shadow-[inset_0_0_0_1px_#8fca7c]" : "bg-white/[0.04] text-slate-300 hover:bg-white/[0.08]"}`}>
                <OptionIcon id={o} />{C.options[o]}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 xl:grid-cols-1 xl:content-center">
        {OPTION_IDS.map((o, i) => (
          <button key={o} type="button" onClick={() => setSel(o)} aria-pressed={sel === o}
            className={`side-card text-left ${sel === o ? "is-on" : ""}`} style={{ "--i": i } as React.CSSProperties}>
            <span className="flex items-baseline justify-between px-1.5 py-1 text-[10px] font-semibold text-slate-300">
              {C.cards[o]}<span className="font-mono text-leaf-300">{OPTIONS[o].goal}</span>
            </span>
            <MiniPitch path={OPTIONS[o].d} tone={o === "shot" ? "#f8fafc" : "#d4ee8f"} dashed={o === "shot"} />
          </button>
        ))}
      </div>
    </div>
  );
}

function StepArt({ i }: { i: number }) {
  const c = { fill: "none", stroke: "#8fca7c", strokeWidth: 1.4 } as const;
  if (i === 0) {
    return (
      <div className="w-24 shrink-0">
        <MiniPitch path="M 22.8 37 Q 21 25 11.8 20.5" crop players={false}
          extra={<><circle cx={22.8} cy={37} r={2} fill="#facc15" /><circle cx={11.8} cy={20.5} r={2} fill="#d4ee8f" /></>} />
      </div>
    );
  }
  if (i === 1) {
    return (
      <svg viewBox="0 0 80 64" className="w-24 shrink-0" aria-hidden>
        <circle cx={40} cy={32} r={20} {...c} strokeDasharray="3 3" />
        {[[40, 12], [60, 32], [40, 52], [20, 32]].map(([x, y], k) => <rect key={k} x={x - 4} y={y - 4} width={8} height={8} fill={k % 2 ? "#f59e0b" : "#38bdf8"} />)}
        <rect x={36} y={28} width={8} height={8} fill="#d4ee8f" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 80 64" className="w-24 shrink-0" aria-hidden>
      <path d="M8 32 H30 M30 32 L52 12 M30 32 H52 M30 32 L52 52" {...c} />
      {[[56, 12], [56, 32], [56, 52]].map(([x, y], k) => <rect key={k} x={x - 4} y={y - 4} width={8} height={8} fill="none" stroke="#d4ee8f" strokeWidth={1.4} />)}
      <rect x={4} y={28} width={8} height={8} fill="#facc15" />
    </svg>
  );
}

function AgentIcon({ i }: { i: number }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      {i === 0 && <path d="M4 18 L10 12 L13 15 L20 6 M15 6h5v5" {...STROKE} />}
      {i === 1 && <path d="M12 3 L19 6 V11 C19 16 15.5 19.5 12 21 C8.5 19.5 5 16 5 11 V6 Z" {...STROKE} />}
      {i === 2 && <><rect x={4} y={4} width={16} height={16} {...STROKE} /><path d="M8 15 L11 11 L13 13 L16 9" {...STROKE} /></>}
      {i === 3 && <path d="M5 12.5 L10 17 L19 7" {...STROKE} />}
      {i === 4 && <><path d="M6 3h9l3 3v15H6z" {...STROKE} /><path d="M9 10h6M9 14h6M9 18h4" {...STROKE} /></>}
    </svg>
  );
}

/** Flat illustrations for the three audiences (no photography: the matches are synthetic). */
function PerspArt({ i }: { i: number }) {
  if (i === 0) {
    // The view from the stand: floodlights, the pitch beyond, supporters in the foreground.
    return (
      <div className="relative overflow-hidden bg-[#07110b]">
        <div className="persp-tilt bg-transparent pb-[22%]">
          <MiniPitch path={OPTIONS.pass.d} />
        </div>
        <span className="pointer-events-none absolute -top-6 left-[8%] h-16 w-16 rounded-full bg-[radial-gradient(rgba(212,238,143,0.35),transparent_70%)]" />
        <span className="pointer-events-none absolute -top-6 right-[8%] h-16 w-16 rounded-full bg-[radial-gradient(rgba(212,238,143,0.35),transparent_70%)]" />
        <svg viewBox="0 0 200 40" className="absolute inset-x-0 bottom-0 block h-auto w-full" aria-hidden>
          <defs>
            <linearGradient id="stand-glow" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#1e3a26" stopOpacity="0" />
              <stop offset="0.45" stopColor="#1e3a26" stopOpacity="0.95" />
              <stop offset="1" stopColor="#0f2216" />
            </linearGradient>
          </defs>
          <rect y={0} width={200} height={40} fill="url(#stand-glow)" />
          {Array.from({ length: 17 }).map((_, k) => {
            const x = k * 12.5 + (k % 2) * 3;
            const up = k % 4 === 1;
            return (
              <g key={k} fill="#030805">
                <circle cx={x} cy={up ? 14 : 18} r={5} />
                <path d={`M ${x - 8} 40 Q ${x - 7} ${up ? 20 : 24} ${x} ${up ? 21 : 25} Q ${x + 7} ${up ? 20 : 24} ${x + 8} 40 Z`} />
                {up && <path d={`M ${x - 4} 18 L ${x - 7} 4 M ${x + 4} 18 L ${x + 7} 4`} stroke="#030805" strokeWidth={2.6} strokeLinecap="round" />}
                {k % 5 === 2 && <rect x={x - 6} y={27} width={12} height={2.5} fill="#5f9c5e" />}
              </g>
            );
          })}
        </svg>
      </div>
    );
  }
  if (i === 1) {
    return (
      <div className="persp-tilt">
        <MiniPitch path="M 22.8 37 Q 21 25 11.8 20.5" extra={<>
          <line x1={22.8} y1={37} x2={11.8} y2={20.5} stroke="#22c55e" strokeWidth={0.5} strokeDasharray="1 1" />
          <line x1={22.8} y1={37} x2={13.9} y2={62.4} stroke="#ef4444" strokeWidth={0.5} strokeDasharray="1 1" />
          <circle cx={22.8} cy={37} r={6} fill="rgba(239,68,68,0.08)" stroke="#ef4444" strokeWidth={0.3} strokeDasharray="0.8 0.6" />
        </>} />
      </div>
    );
  }
  return (
    <div className="relative bg-[#07110b] px-[17%] pb-[6%] pt-[4%]">
      <div className="relative ring-2 ring-slate-700">
        <MiniPitch path={OPTIONS.pass.d} />
        <span className="absolute bottom-[8%] left-[4%] bg-leaf-600 px-1.5 py-0.5 font-mono text-[9px] font-bold text-white">WHAT IF · PASS 2.0%</span>
      </div>
      <div className="mx-auto h-1.5 w-[12%] bg-slate-700" />
    </div>
  );
}

function SectionHead({ eyebrow, title, sub, id }: { eyebrow: string; title: readonly string[] | string; sub?: string; id: string }) {
  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,0.8fr)] md:items-end">
      <div>
        <p className="eyebrow" id={id}>{eyebrow}</p>
        <h2 className="mt-3 text-[clamp(1.7rem,3.4vw,2.6rem)] font-extrabold leading-[1.08] text-white">
          {typeof title === "string" ? title : <>{title[0]}<br />{title[1]}</>}
        </h2>
      </div>
      {sub && <p className="max-w-md text-[14px] leading-relaxed text-slate-400 md:justify-self-end">{sub}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------ */

export default function Landing() {
  const [lang, setLang] = useState<Lang>("en");
  const [sel, setSel] = useState<OptionId>("pass");
  const [playKey, setPlayKey] = useState(0);
  const C = COPY[lang];
  useEffect(() => {
    // Older links put app state on the root URL: forward them to the app.
    const q = window.location.search;
    if (/[?&](scenario|view)=/.test(q)) window.location.replace(`/app/${q}`);
    if (navigator.language?.toLowerCase().startsWith("nl")) setLang("nl");
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  return (
    <div className={`landing ${display.variable} ${body.variable} min-h-screen overflow-x-hidden`}>
      <header className="sticky top-0 z-30 border-b border-white/[0.05] bg-ink/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1320px] items-center gap-6 px-5 py-3">
          <a href="#top" className="flex items-center gap-2">
            <BrandMark size={28} id="land" />
            <span className="text-[14px] font-black tracking-[0.32em] text-white">PARALLEL</span>
          </a>
          <nav className="mx-auto hidden items-center gap-7 text-[13px] text-slate-400 md:flex" aria-label="Sections">
            {C.nav.map(([href, label]) => <a key={href} href={href} className="transition hover:text-white">{label}</a>)}
          </nav>
          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <div role="radiogroup" aria-label="Language" className="flex bg-white/[0.04] p-0.5">
              {(["en", "nl"] as const).map((l) => (
                <button key={l} type="button" role="radio" aria-checked={lang === l} onClick={() => setLang(l)} className="tab px-2 py-1 text-[11px]">{l.toUpperCase()}</button>
              ))}
            </div>
            <Link href={APP} className="btn btn-primary whitespace-nowrap px-4 py-2">{C.open} →</Link>
          </div>
        </div>
      </header>

      <section id="top" className="relative mx-auto grid max-w-[1320px] scroll-mt-20 items-center gap-8 px-5 pb-16 pt-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:pt-14">
        <div className="relative z-10 animate-rise">
          <p className="eyebrow">{C.eyebrow}</p>
          <h1 className="mt-4 text-[clamp(2.1rem,4vw,3.5rem)] font-extrabold leading-[1.04] text-white">
            {C.title[0]}<br /><span className="extrude text-leaf-300">{C.title[1]}</span>
          </h1>
          <p className="mt-5 max-w-md text-[15px] leading-relaxed text-slate-400">{C.sub}</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href={LINKS.multiverse} className="btn btn-primary px-5 py-3 text-sm" data-testid="cta-multiverse">{C.explore} ↗</Link>
            <Link href={LINKS.demo} className="btn px-5 py-3 text-sm" data-testid="cta-demo">▶ {C.demo}</Link>
          </div>
          <dl className="mt-10 grid max-w-md grid-cols-3 divide-x divide-white/[0.07]">
            {C.stats.map(([v, k]) => (
              <div key={k} className="px-3 first:pl-0">
                <dt className="sr-only">{k}</dt>
                <dd className="num font-mono text-2xl font-bold text-white">{v}</dd>
                <dd className="mt-1 text-[11px] leading-snug text-slate-500">{k}</dd>
              </div>
            ))}
          </dl>
        </div>
        <HeroScene C={C} sel={sel} setSel={setSel} />
      </section>

      <section className="section-band">
        <div className="mx-auto max-w-[1320px] px-5 py-16">
          <SectionHead eyebrow={C.howEyebrow} title={C.howTitle} sub={C.howSub} id="how" />
          <ol className="mt-10 grid gap-4 md:grid-cols-3">
            {C.steps.map(([title, text], i) => (
              <li key={title} className="glass relative flex items-center gap-4 p-5">
                <span className="grid h-9 w-9 shrink-0 place-items-center self-start bg-leaf-500/15 font-mono text-sm font-bold text-leaf-300 ring-1 ring-leaf-400/40">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="text-[15px] font-bold text-white">{title}</h3>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-slate-400">{text}</p>
                </div>
                <StepArt i={i} />
                {i < 2 && <span className="absolute -right-3.5 top-1/2 z-10 hidden -translate-y-1/2 text-leaf-400 md:block" aria-hidden>→</span>}
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="section-band">
        <div className="mx-auto max-w-[1320px] px-5 py-16">
          <SectionHead eyebrow={C.agentsEyebrow} title={C.agentsTitle} sub={C.agentsSub} id="agents" />
          <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <ul className="space-y-5">
              {C.agents.map(([name, text], i) => (
                <li key={name} className="flex gap-4">
                  <span className={`grid h-11 w-11 shrink-0 place-items-center ring-1 ${i === 0 ? "bg-leaf-400 text-ink ring-leaf-300" : "text-leaf-300 ring-leaf-400/40"}`}><AgentIcon i={i} /></span>
                  <div>
                    <h3 className="text-[14px] font-bold text-white">{name}</h3>
                    <p className="mt-0.5 text-[13px] leading-relaxed text-slate-400">{text}</p>
                  </div>
                </li>
              ))}
            </ul>
            <div className="glass p-5">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-[15px] font-bold text-white">{C.battle}</h3>
                <span className="chip text-slate-300">{C.battleAt}</span>
              </div>
              <div className="mt-4 grid items-center gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
                {[C.attack, C.defend].map(([who, what], k) => (
                  <div key={who} className={`bg-white/[0.03] p-3 ring-1 ${k ? "ring-orange-400/30 sm:order-3" : "ring-leaf-400/30"}`}>
                    <div className="flex items-center gap-2 text-[13px] font-bold text-white">
                      <span className={`grid h-6 w-6 place-items-center ${k ? "bg-orange-400/20 text-orange-300" : "bg-leaf-400/20 text-leaf-300"}`}><AgentIcon i={k} /></span>{who}
                    </div>
                    <p className="mt-1 text-[12px] text-slate-400">{what}</p>
                    <div className="mt-3">
                      <MiniPitch crop path={k ? undefined : "M 22.8 37 Q 21 25 11.8 20.5"} extra={k ? <>
                        <path d="M 21.6 37.2 L 17.5 29.5" stroke="#f97316" strokeWidth={0.7} strokeDasharray="1 0.7" />
                        <path d="M 20.3 38 L 16 31.5" stroke="#f97316" strokeWidth={0.7} strokeDasharray="1 0.7" />
                        <line x1={22.8} y1={37} x2={11.8} y2={20.5} stroke="rgba(248,250,252,0.35)" strokeWidth={0.5} strokeDasharray="1 1" />
                      </> : undefined} />
                    </div>
                  </div>
                ))}
                <span className="grid h-9 w-9 place-items-center justify-self-center bg-white/[0.06] font-mono text-[11px] font-bold text-white ring-1 ring-white/15 sm:order-2">VS</span>
              </div>
              <p className="mt-5 font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">{C.result}</p>
              <div className="mt-2 grid grid-cols-3 gap-4">
                {C.metrics.map(([v, k, w]) => (
                  <div key={k}>
                    <div className="num font-mono text-lg font-bold text-white">{v}</div>
                    <div className="text-[11px] leading-snug text-slate-500">{k}</div>
                    <div className="mt-2 h-1 bg-white/[0.06]"><div className="h-full bg-leaf-400" style={{ width: `${Math.max(4, w * 100)}%` }} /></div>
                  </div>
                ))}
              </div>
              <div className="mt-5 flex gap-3 bg-white/[0.03] p-3 ring-1 ring-white/[0.06]">
                <span className="grid h-8 w-8 shrink-0 place-items-center bg-leaf-400/15 text-leaf-300" aria-hidden>◆</span>
                <div>
                  <div className="text-[13px] font-bold text-white">{C.insightTitle}</div>
                  <p className="mt-0.5 text-[12px] leading-relaxed text-slate-400">{C.insight}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section-band">
        <div className="mx-auto max-w-[1320px] px-5 py-16">
          <SectionHead eyebrow={C.compareEyebrow} title={C.compareTitle} sub={C.compareSub} id="compare" />
          <div className="relative mt-10 grid gap-4 md:grid-cols-2">
            {[
              { label: C.actualMatch, caption: C.actualCaption, d: OPTIONS.shot.d, tone: "#f8fafc", on: false },
              { label: C.yourAlt, caption: C.altCaption, d: "M 22.8 37 Q 21 25 11.8 20.5", tone: "#d4ee8f", on: true },
            ].map((p) => (
              <figure key={p.label} className="glass p-2">
                <div className="relative">
                  <span className={`absolute left-2 top-2 z-10 px-2 py-0.5 text-[11px] font-bold ${p.on ? "bg-leaf-500 text-white" : "bg-slate-950/85 text-white ring-1 ring-white/15"}`}>{p.label}</span>
                  <MiniPitch path={p.d} tone={p.tone} animKey={playKey} view="-1 12 70 34" dot={0.85} />
                </div>
                <figcaption className="flex items-center gap-3 px-1 pb-1 pt-2.5">
                  <button type="button" onClick={() => setPlayKey((k) => k + 1)} aria-label={C.play}
                    className="grid h-8 w-8 shrink-0 place-items-center bg-white text-[11px] text-ink hover:bg-leaf-100">▶</button>
                  <span className="text-[12px] text-slate-300">{p.caption}</span>
                  <span className="relative ml-auto h-1 w-1/2 bg-white/[0.08]"><span key={playKey} className="progress-fill absolute inset-y-0 left-0 bg-leaf-400" /></span>
                </figcaption>
              </figure>
            ))}
            <span className="absolute left-1/2 top-[42%] z-10 hidden h-9 w-9 -translate-x-1/2 place-items-center bg-white text-sm font-bold text-ink md:grid" aria-hidden>⇄</span>
          </div>
        </div>
      </section>

      <section className="section-band">
        <div className="mx-auto max-w-[1320px] px-5 py-16">
          <SectionHead eyebrow={C.perspEyebrow} title={C.perspTitle} id="perspectives" />
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {C.persp.map(([title, text], i) => (
              <Link key={title} href={[LINKS.fans, LINKS.analysts, LINKS.broadcast][i]} className="glass group block overflow-hidden transition hover:-translate-y-1">
                <div className="flex gap-3 p-4">
                  <span className="grid h-9 w-9 shrink-0 place-items-center text-leaf-300 ring-1 ring-leaf-400/40" aria-hidden>{["◉", "▥", "▣"][i]}</span>
                  <div>
                    <h3 className="text-[15px] font-bold text-white">{title} <span className="text-leaf-400 opacity-0 transition group-hover:opacity-100">→</span></h3>
                    <p className="mt-0.5 text-[12.5px] leading-relaxed text-slate-400">{text}</p>
                  </div>
                </div>
                <div className="border-t border-white/[0.06]"><PerspArt i={i} /></div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="final-band relative overflow-hidden">
        <div className="mx-auto grid max-w-[1320px] items-center gap-10 px-5 py-20 lg:grid-cols-2">
          <div className="relative z-10">
            <p className="eyebrow">{C.finalEyebrow}</p>
            <h2 className="mt-3 text-[clamp(1.9rem,3.8vw,3rem)] font-extrabold leading-[1.06] text-white">
              {C.finalTitle[0]} <span className="text-leaf-300">{C.finalTitle[1]}</span>
            </h2>
            <p className="mt-4 max-w-md text-[15px] leading-relaxed text-slate-400">{C.finalSub}</p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link href={LINKS.multiverse} className="btn btn-primary px-5 py-3 text-sm">{C.explore} ↗</Link>
              <Link href={LINKS.demo} className="btn px-5 py-3 text-sm">▶ {C.demo}</Link>
            </div>
          </div>
          <div className="float-field" aria-hidden>
            {(["shot", "pass", "switch", "pass", "shot", "switch"] as OptionId[]).map((o, i) => (
              <div key={i} className="float-card" style={{ "--i": i } as React.CSSProperties}>
                <MiniPitch path={OPTIONS[o].d} tone={o === "shot" ? "#f8fafc" : "#d4ee8f"} dashed={o === "shot"} />
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="mx-auto max-w-[1320px] px-5 pb-10 pt-6">
        <p className="text-center text-[11px] leading-relaxed text-slate-600">{C.note}</p>
      </footer>
    </div>
  );
}

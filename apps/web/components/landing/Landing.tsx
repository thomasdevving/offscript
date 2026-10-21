"use client";

import { Space_Grotesk, Unbounded } from "next/font/google";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import BrandMark from "../BrandMark";
import ThemeToggle from "../ThemeToggle";

type Lang = "en" | "nl";

// Landing-only type: a wide geometric display face for headlines, a grotesk for body copy.
const display = Unbounded({ subsets: ["latin"], variable: "--font-display", display: "swap" });
const body = Space_Grotesk({ subsets: ["latin"], variable: "--font-body", display: "swap" });

const COPY = {
  en: {
    eyebrow: "Counterfactual football intelligence",
    title: ["Every decision", "creates another game."],
    sub: "OFFSCRIPT freezes the moment a player decides, plays every option forward hundreds of times and lets a team of agents explain which future was more promising, with the evidence on the table.",
    live: "Watch the live match",
    multiverse: "Enter the Multiverse",
    open: "Open app",
    stats: [
      ["200", "simulations per option"],
      ["5", "agents, one verified answer"],
      ["3", "viewer modes, EN and NL"],
    ],
    howEyebrow: "How it works",
    howTitle: ["From one moment", "to many possibilities."],
    howSub: "You choose a decision, the agents compete with strategies, the simulator explores the outcomes, and you rewind, compare and discover what could have happened.",
    steps: [
      ["Choose", "Change the decision, or let the agents suggest the alternatives."],
      ["Simulate", "Attacking and defending agents plan against each other; every option runs hundreds of times."],
      ["Explore", "Compare outcomes, read the tactical explanation and continue to the next decision."],
    ],
    compareEyebrow: "Compare realities",
    compareTitle: ["See how the game", "could have unfolded."],
    compareSub: "Watch the actual outcome and your alternative side by side. Different decisions. Different strategies. Different futures.",
    actualMatch: "Actual match",
    yourAlt: "Your alternative",
    actualCaption: "72:49 · Shot blocked",
    altCaption: "72:49 · Pass completed",
    play: "Play",
    agentsEyebrow: "The agent team",
    agentsTitle: "Five specialists, one pipeline.",
    agentsSub: "Watch one real run on the 73' decision: each agent does its part, hands the baton on, and nothing reaches the screen before it is verified.",
    relayFoot: "Real run of the 73' scenario · deterministic planner · 6 agent runs · 7 tool calls",
    relay: [
      { ms: "49 ms", handoff: "analyse (high priority)", body: "Castellane shoots from 23 m while Mbeki-Larsen is free on the right. Three triggers fire, so the moment is worth a full analysis.",
        tags: ["Shot while a teammate was available", "High-value attacking possession", "Decision under pressure"] },
      { ms: "112 ms", handoff: "2 alternatives + observed action", body: "From the frozen snapshot it proposes only options that are actually on: the pass to Mbeki-Larsen and the pass to Kestrel, next to the shot that was taken." },
      { ms: "7.2 s", handoff: "200 rollouts/option ready", body: "Every option is played forward 200 times from the same frozen state with paired random seeds, so the options are compared fairly." },
      { ms: "8 ms", handoff: "analysis verified", body: "It recomputes the figures and checks every claim against the evidence table. Anything the numbers do not support is rejected.",
        checks: ["Every candidate is feasible from the snapshot", "Figures match the simulation results", "Claims match the evidence table"] },
      { ms: "5 ms", handoff: "6 narratives drafted", body: "The verified result becomes three stories, for fans, analysts and broadcast, in English and Dutch, and goes back for one more check." },
    ],
    modes: ["Fan", "Analyst", "Broadcast"],
    agents: [
      ["Decision", "spots the moment that mattered"],
      ["Strategy", "proposes the realistic options"],
      ["Simulation", "plays each option forward"],
      ["Verification", "rejects claims the data does not support"],
      ["Explanation", "tells the story for fans, analysts or broadcast"],
    ],
    ctaTitle: "Take the decision yourself.",
    ctaBody: "Pick a moment, choose your own pass or shot, and watch the defence respond in a branch of the match that never happened.",
    labels: { actual: "Actual · shoot", alt1: "Pass · model favours", alt2: "Pass to Kestrel" },
    note: "Synthetic matches with fictional teams and players. Simulated outcomes are model estimates, not what would have happened.",
  },
  nl: {
    eyebrow: "Contrafactische voetbalintelligentie",
    title: ["Elke beslissing", "creëert een andere wedstrijd."],
    sub: "OFFSCRIPT bevriest het moment waarop een speler beslist, speelt elke optie honderden keren vooruit en laat een team van agents uitleggen welke toekomst kansrijker was, met het bewijs op tafel.",
    live: "Bekijk de live wedstrijd",
    multiverse: "Betreed het Multiverse",
    open: "Open app",
    stats: [
      ["200", "simulaties per optie"],
      ["5", "agents, één geverifieerd antwoord"],
      ["3", "kijkmodi, EN en NL"],
    ],
    howEyebrow: "Hoe het werkt",
    howTitle: ["Van één moment", "naar talloze mogelijkheden."],
    howSub: "Jij kiest een beslissing, de agents strijden met strategieën, de simulator verkent de uitkomsten en jij spoelt terug, vergelijkt en ontdekt wat er had kunnen gebeuren.",
    steps: [
      ["Kiezen", "Verander de beslissing, of laat de agents de alternatieven voorstellen."],
      ["Simuleren", "Aanvallende en verdedigende agents plannen tegen elkaar; elke optie wordt honderden keren gespeeld."],
      ["Verkennen", "Vergelijk uitkomsten, lees de tactische uitleg en ga door naar de volgende beslissing."],
    ],
    compareEyebrow: "Vergelijk werkelijkheden",
    compareTitle: ["Zie hoe de wedstrijd", "had kunnen verlopen."],
    compareSub: "Bekijk de echte uitkomst en jouw alternatief naast elkaar. Andere beslissingen. Andere strategieën. Andere toekomsten.",
    actualMatch: "Echte wedstrijd",
    yourAlt: "Jouw alternatief",
    actualCaption: "72:49 · Schot geblokt",
    altCaption: "72:49 · Pass aangekomen",
    play: "Afspelen",
    agentsEyebrow: "Het agentteam",
    agentsTitle: "Vijf specialisten, één pijplijn.",
    agentsSub: "Bekijk één echte run op de 73'-beslissing: elke agent doet zijn deel, geeft het stokje door, en niets komt in beeld voordat het geverifieerd is.",
    relayFoot: "Echte run van het 73'-scenario · deterministische planner · 6 agent-runs · 7 tool-aanroepen",
    relay: [
      { ms: "49 ms", handoff: "analyseren (hoge prioriteit)", body: "Castellane schiet van 23 m terwijl Mbeki-Larsen rechts vrij staat. Drie triggers slaan aan, dus het moment krijgt een volledige analyse.",
        tags: ["Schot terwijl een medespeler vrij stond", "Waardevol aanvalsbezit", "Beslissing onder druk"] },
      { ms: "112 ms", handoff: "2 alternatieven + echte actie", body: "Vanuit de bevroren momentopname stelt hij alleen opties voor die echt kunnen: de pass naar Mbeki-Larsen en de pass naar Kestrel, naast het schot dat genomen werd." },
      { ms: "7,2 s", handoff: "200 simulaties per optie klaar", body: "Elke optie wordt 200 keer vooruitgespeeld vanuit dezelfde bevroren situatie met gepaarde toevalsgetallen, zodat de opties eerlijk vergeleken worden." },
      { ms: "8 ms", handoff: "analyse geverifieerd", body: "Hij rekent de cijfers na en toetst elke bewering aan de bewijstabel. Wat de cijfers niet steunen, wordt afgewezen.",
        checks: ["Elke kandidaat is uitvoerbaar vanuit de momentopname", "Cijfers kloppen met de simulatieresultaten", "Beweringen kloppen met de bewijstabel"] },
      { ms: "5 ms", handoff: "6 verhalen geschreven", body: "Het geverifieerde resultaat wordt drie verhalen, voor fans, analisten en omroep, in het Engels en Nederlands, en gaat nog één keer langs de controle." },
    ],
    modes: ["Fan", "Analist", "Omroep"],
    agents: [
      ["Decision", "vindt het moment dat ertoe deed"],
      ["Strategy", "stelt de realistische opties voor"],
      ["Simulation", "speelt elke optie vooruit"],
      ["Verification", "verwerpt claims die de data niet steunt"],
      ["Explanation", "vertelt het verhaal voor fans, analisten of omroep"],
    ],
    ctaTitle: "Neem de beslissing zelf.",
    ctaBody: "Kies een moment, bepaal je eigen pass of schot en zie de verdediging reageren in een tak van de wedstrijd die nooit heeft plaatsgevonden.",
    labels: { actual: "Echt · schot", alt1: "Pass · model kiest", alt2: "Pass naar Kestrel" },
    note: "Synthetische wedstrijden met fictieve teams en spelers. Gesimuleerde uitkomsten zijn modelschattingen, geen werkelijkheid.",
  },
} as const;

const APP = "/app/?scenario=shoot_vs_pass";

// Players in pitch metres (105 x 68): home attacks left, matching the in-app decision.
const HOME = [[24, 37, 9], [33, 22, 7], [30, 52, 11], [46, 30, 8], [48, 44, 6], [60, 20, 2], [58, 54, 4], [80, 34, 1]] as const;
const AWAY = [[12, 36, 1], [19, 30, 4], [19, 42, 5], [27, 33, 8], [36, 26, 10], [37, 49, 7], [40, 14, 11]] as const;
const DECISION: [number, number] = [26, 36];

function Markings({ glow }: { glow?: boolean }) {
  return (
    <g fill="none" stroke={glow ? "#8fca7c" : "rgba(238,246,234,0.75)"} strokeWidth={glow ? 0.35 : 0.3} opacity={glow ? 0.55 : 1}>
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

const pos = (x: number, y: number) => ({ left: `${(x / 105) * 100}%`, top: `${(y / 68) * 100}%` });

// The real frozen snapshot of the 73' scenario (demo-match-073, 72:47), for the flat thumbnails below.
const SNAP_HOME: Pt2[] = [[82.5, 34], [32.4, 9.4], [54.3, 47], [54.2, 27.8], [37.9, 66], [38, 32.4], [30.1, 31.2], [22.8, 37], [11.8, 20.5], [13.9, 62.4], [12.2, 32]];
const SNAP_AWAY: Pt2[] = [[3.2, 34.4], [13.8, 57.7], [11.4, 34.4], [12.4, 37.6], [11.5, 30.4], [21.6, 37.2], [20.3, 38], [32.6, 27.1], [28.6, 58.5], [34.7, 12.9], [39.7, 35.6]];
type Pt2 = [number, number];
const SHOT_PATH = "M 22.8 37 L 13.5 36.2";
const PASS_PATH = "M 22.8 37 Q 21 25 11.8 20.5";

function MiniPitch({ path, tone = "#8fca7c", dashed, crop, view, players = true, extra, animKey, dot = 1.3 }: {
  path?: string; tone?: string; dashed?: boolean; crop?: boolean; view?: string; players?: boolean; extra?: React.ReactNode; animKey?: number; dot?: number;
}) {
  return (
    <svg viewBox={view ?? (crop ? "-1 8 64 48" : "-2 -2 109 72")} className="block h-auto w-full" aria-hidden>
      <rect x={-2} y={-2} width={109} height={72} fill="#0f3a26" />
      {[0, 2, 4, 6, 8].map((i) => <rect key={i} x={i * 10.5} y={0} width={10.5} height={68} fill="#134330" />)}
      <g fill="none" stroke="rgba(238,246,234,0.45)" strokeWidth={0.35}>
        <rect x={0} y={0} width={105} height={68} />
        <line x1={52.5} y1={0} x2={52.5} y2={68} />
        <circle cx={52.5} cy={34} r={9.15} />
        <rect x={0} y={13.85} width={16.5} height={40.3} />
        <rect x={88.5} y={13.85} width={16.5} height={40.3} />
        <rect x={0} y={24.85} width={5.5} height={18.3} />
        <rect x={99.5} y={24.85} width={5.5} height={18.3} />
      </g>
      {players && SNAP_HOME.map(([x, y], k) => <circle key={`h${k}`} cx={x} cy={y} r={dot} fill="#38bdf8" />)}
      {players && SNAP_AWAY.map(([x, y], k) => <circle key={`a${k}`} cx={x} cy={y} r={dot} fill="#f59e0b" />)}
      {path && (
        <path key={animKey} d={path} fill="none" stroke={tone} strokeWidth={0.8} strokeLinecap="round" pathLength={100}
          strokeDasharray={dashed ? "1.6 1.2" : undefined} className={dashed ? "" : "draw-path"} style={{ filter: `drop-shadow(0 0 1px ${tone})` }} />
      )}
      {extra}
    </svg>
  );
}

function StepArt({ i }: { i: number }) {
  const c = { fill: "none", stroke: "#8fca7c", strokeWidth: 1.4 } as const;
  if (i === 0) {
    return (
      <div className="w-24 shrink-0">
        <MiniPitch path={PASS_PATH} crop players={false}
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

function SectionHead({ eyebrow, title, sub }: { eyebrow: string; title: readonly string[]; sub: string }) {
  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,0.8fr)] md:items-end">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2 className="mt-3 text-[clamp(1.7rem,3.4vw,2.6rem)] font-extrabold leading-[1.08] text-white">{title[0]}<br />{title[1]}</h2>
      </div>
      <p className="max-w-md text-[14px] leading-relaxed text-slate-400 md:justify-self-end">{sub}</p>
    </div>
  );
}

function Pin({ x, y, n, team }: { x: number; y: number; n: number; team: "home" | "away" }) {
  return (
    <div className="pin" style={pos(x, y)}>
      <span className="pin-shadow" />
      <span className="billboard pin-body">
        <span className={`pin-head ${team === "home" ? "bg-sky-400 text-sky-950" : "bg-amber-400 text-amber-950"}`}>{n}</span>
        <span className="pin-stem" />
      </span>
    </div>
  );
}

function BranchLayer({ z, d, end, label, tone, delay }: { z: number; d: string; end: [number, number]; label: string; tone: string; delay: number }) {
  return (
    <div className="layer branch" style={{ "--z": `${z}px`, animationDelay: `${delay}s` } as React.CSSProperties}>
      <svg viewBox="-1 -1 107 70" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
        <Markings glow />
        <path d={d} fill="none" stroke={tone} strokeWidth={0.8} strokeDasharray="1.6 1.1" className="branch-path" />
        <circle cx={DECISION[0]} cy={DECISION[1]} r={1.6} fill="none" stroke={tone} strokeWidth={0.4} />
        <circle cx={end[0]} cy={end[1]} r={1.1} fill={tone} />
      </svg>
      <div className="anchor3d" style={pos(end[0], end[1])}>
        <span className="billboard tag3d" style={{ borderColor: tone, color: tone }}>{label}</span>
      </div>
    </div>
  );
}

/** The hero: one frozen pitch with two parallel futures floating above it, tilting with the pointer. */
function MultiverseScene({ lang }: { lang: Lang }) {
  const ref = useRef<HTMLDivElement>(null);
  const L = COPY[lang].labels;
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      const nx = (e.clientX - r.left) / r.width - 0.5;
      const ny = (e.clientY - r.top) / r.height - 0.5;
      el.style.setProperty("--rx", `${(nx * 14).toFixed(2)}deg`);
      el.style.setProperty("--ry", `${(-ny * 10).toFixed(2)}deg`);
    };
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, []);
  return (
    <div ref={ref} className="scene" aria-hidden>
      <div className="stage">
        <div className="layer base">
          <svg viewBox="-1 -1 107 70" className="absolute inset-0 h-full w-full" aria-hidden>
            <Markings />
            <line x1={DECISION[0]} y1={DECISION[1]} x2={2} y2={34} stroke="#f8fafc" strokeWidth={0.6} strokeDasharray="1.4 1" opacity={0.9} />
          </svg>
          {HOME.map(([x, y, n]) => <Pin key={`h${n}`} x={x} y={y} n={n} team="home" />)}
          {AWAY.map(([x, y, n]) => <Pin key={`a${n}`} x={x} y={y} n={n} team="away" />)}
          <div className="anchor3d" style={pos(8, 25)}>
            <span className="billboard tag3d border-white/60 text-white">{L.actual} · 0.0%</span>
          </div>
          {/* The time beam: every future grows out of the same frozen moment. */}
          <span className="beam" style={pos(DECISION[0], DECISION[1])} />
        </div>
        <BranchLayer z={120} d={`M ${DECISION[0]} ${DECISION[1]} Q 30 18 33 22 L 8 31`} end={[8, 31]} label={`${L.alt1} · 2.0%`} tone="#8fca7c" delay={0} />
        <BranchLayer z={230} d={`M ${DECISION[0]} ${DECISION[1]} Q 22 46 30 52`} end={[30, 52]} label={`${L.alt2} · 0.0%`} tone="#cfe2b4" delay={1.2} />
      </div>
    </div>
  );
}

function Cube({ label, i }: { label: string; i: number }) {
  return (
    <div className="cube-wrap">
      <div className="cube" style={{ animationDelay: `${-i * 1.6}s` }}>
        {["front", "back", "right", "left", "top", "bottom"].map((f) => (
          <span key={f} className={`face ${f}`}>{f === "front" || f === "back" ? String(i + 1).padStart(2, "0") : ""}</span>
        ))}
      </div>
      <span className="sr-only">{label}</span>
    </div>
  );
}

/** What each agent produced on the 73' decision, drawn small. */
function RelayArt({ i, C }: { i: number; C: (typeof COPY)[Lang] }) {
  const step = C.relay[i];
  if (i === 0) {
    return (
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] sm:items-center">
        <MiniPitch crop players extra={<>
          <circle cx={22.8} cy={37} r={3.2} fill="none" stroke="#facc15" strokeWidth={0.6} />
          <circle cx={11.8} cy={20.5} r={3.2} fill="none" stroke="#d4ee8f" strokeWidth={0.6} strokeDasharray="1 0.8" />
        </>} />
        <ul className="space-y-1.5">{"tags" in step && step.tags.map((t) => <li key={t} className="chip text-leaf-300">{t}</li>)}</ul>
      </div>
    );
  }
  if (i === 1) {
    return (
      <MiniPitch crop extra={<>
        <path d={SHOT_PATH} stroke="#f8fafc" strokeWidth={0.6} strokeDasharray="1.4 1" fill="none" />
        <path d={PASS_PATH} stroke="#d4ee8f" strokeWidth={0.7} fill="none" className="draw-path" pathLength={100} />
        <path d="M 22.8 37 Q 22 50 14 54" stroke="#cfe2b4" strokeWidth={0.6} strokeDasharray="0.8 0.7" fill="none" />
      </>} />
    );
  }
  if (i === 2) {
    const bars: [string, number, string][] = [["Shoot · actual", 0, "0.0%"], ["Pass to Mbeki-Larsen", 0.02, "2.0%"], ["Pass to Kestrel", 0, "0.0%"]];
    return (
      <div className="space-y-2.5">
        {bars.map(([k, v, l], j) => (
          <div key={k} className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)_3rem] items-center gap-3 text-[12px]">
            <span className="truncate text-slate-300">{k}</span>
            <span className="h-2.5 bg-white/[0.06]"><span key={i} className="relay-bar block h-full bg-leaf-400" style={{ width: `${Math.max(2, (v / 0.025) * 100)}%`, animationDelay: `${j * 120}ms` }} /></span>
            <span className="text-right font-mono text-white">{l}</span>
          </div>
        ))}
        <p className="font-mono text-[10px] text-slate-500">P(goal within 10 s) · 200 paired rollouts each</p>
      </div>
    );
  }
  if (i === 3) {
    return (
      <ul className="space-y-2">
        {"checks" in step && step.checks.map((c, j) => (
          <li key={c} className="relay-check flex items-center gap-2 text-[12.5px] text-slate-200" style={{ animationDelay: `${j * 220}ms` }}>
            <span className="grid h-5 w-5 shrink-0 place-items-center bg-leaf-500 text-[11px] font-bold text-white">✓</span>{c}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {[
        ["Was there a better option?", "Under our simulation model, a pass to Mbeki-Larsen led to a goal within 10 seconds in 2.0% of 200 simulated continuations."],
        ["Pass to Mbeki-Larsen", "+2.0 pp [+0.1, +3.9] vs the shot · more promising under the model"],
        ["THE OTHER OPTION", "Model: pass to Mbeki-Larsen 2.0% vs 0.0% for the shot (200 sims)"],
      ].map(([h, b], j) => (
        <div key={h} className="relay-check bg-white/[0.04] p-2.5 ring-1 ring-white/[0.06]" style={{ animationDelay: `${j * 160}ms` }}>
          <div className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-leaf-300">{C.modes[j]}</div>
          <div className="mt-1 text-[12px] font-bold text-white">{h}</div>
          <div className="mt-0.5 text-[11px] leading-snug text-slate-400">{b}</div>
        </div>
      ))}
    </div>
  );
}

/**
 * The agent relay: five stations on one track, a baton moving between them, and below it what the
 * active agent did on the 73' decision. Advances on its own; click a station to take over.
 */
function AgentRelay({ C }: { C: (typeof COPY)[Lang] }) {
  const [active, setActive] = useState(0);
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (held) return;
    const id = setInterval(() => setActive((a) => (a + 1) % C.agents.length), 3600);
    return () => clearInterval(id);
  }, [held, C.agents.length]);
  const step = C.relay[active];
  const n = C.agents.length;
  return (
    <div className="mt-12" onMouseEnter={() => setHeld(true)} onMouseLeave={() => setHeld(false)} data-testid="agent-relay">
      <ol className="relative grid grid-cols-5 gap-2">
        <span className="absolute left-[10%] right-[10%] top-[44px] hidden h-px bg-white/10 sm:block" aria-hidden />
        <span className="absolute left-[10%] top-[44px] hidden h-px bg-leaf-400 transition-all duration-700 sm:block" style={{ width: `${(active / (n - 1)) * 80}%` }} aria-hidden />
        {C.agents.map(([name, role], i) => (
          <li key={name} className="relative flex flex-col items-center text-center">
            <button type="button" onClick={() => { setActive(i); setHeld(true); }} aria-pressed={active === i}
              className={`relay-station flex flex-col items-center ${active === i ? "is-on" : i < active ? "is-done" : ""}`} data-testid={`relay-${i}`}>
              <Cube label={name} i={i} />
              <span className={`mt-2 text-[10.5px] font-black sm:mt-6 sm:text-sm ${active === i ? "text-leaf-300" : "text-white"}`}>{name}<span className="hidden sm:inline"> Agent</span></span>
              <span className="mt-1 hidden max-w-[16rem] text-[12px] leading-snug text-slate-500 sm:block">{role}</span>
              <span className={`mt-2 font-mono text-[10px] ${active === i ? "text-amber-300" : "text-slate-600"}`}>{C.relay[i].ms}</span>
            </button>
          </li>
        ))}
      </ol>
      <div key={active} className="glass mt-8 grid animate-rise gap-6 p-5 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] md:p-6" aria-live="polite">
        <div>
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
            <span className="grid h-6 w-6 place-items-center bg-leaf-500/15 text-[11px] font-bold text-leaf-300 ring-1 ring-leaf-400/40">{String(active + 1).padStart(2, "0")}</span>
            {C.agents[active][0]} Agent · {step.ms}
          </div>
          <p className="mt-3 text-[15px] leading-relaxed text-slate-200">{step.body}</p>
          <div className="mt-4 inline-flex items-center gap-2 bg-white/[0.04] px-2.5 py-1.5 font-mono text-[11px] text-leaf-300 ring-1 ring-white/[0.06]">
            <span className="text-slate-500">handoff</span> → {active < n - 1 ? C.agents[active + 1][0].toLowerCase() : C.agents[3][0].toLowerCase()}: {step.handoff}
          </div>
        </div>
        <RelayArt i={active} C={C} />
      </div>
      <p className="mt-3 text-center font-mono text-[10px] text-slate-500">{C.relayFoot}</p>
    </div>
  );
}

export default function Landing() {
  const [lang, setLang] = useState<Lang>("en");
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
      <header className="relative z-20 mx-auto flex max-w-[1400px] items-center gap-4 px-5 py-4">
        <div className="flex items-center gap-2">
          <BrandMark size={30} id="land" />
          <span className="text-[15px] font-black tracking-[0.32em] text-white">OFFSCRIPT</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div role="radiogroup" aria-label="Language" className="flex rounded-sm bg-white/[0.04] p-0.5">
            {(["en", "nl"] as const).map((l) => (
              <button key={l} type="button" role="radio" aria-checked={lang === l} onClick={() => setLang(l)} className="tab">{l.toUpperCase()}</button>
            ))}
          </div>
          <ThemeToggle lang={lang} />
          <Link href={APP} className="btn whitespace-nowrap">{C.open} →</Link>
        </div>
      </header>

      <section className="relative mx-auto grid max-w-[1400px] items-center gap-6 px-5 pb-10 pt-4 lg:min-h-[calc(100vh-72px)] lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="relative z-10 max-w-xl animate-rise">
          <p className="eyebrow">{C.eyebrow}</p>
          <h1 className="mt-4 text-[clamp(2rem,4.2vw,3.7rem)] font-extrabold leading-[1.02] text-white">
            {C.title[0]}<br /><span className="extrude text-leaf-300">{C.title[1]}</span>
          </h1>
          <p className="mt-6 max-w-lg text-[15px] leading-relaxed text-slate-400">{C.sub}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href={APP} className="btn btn-primary px-6 py-3 text-sm" data-testid="cta-live">{C.live}</Link>
            <Link href={`${APP}&view=multiverse`} className="btn px-6 py-3 text-sm" data-testid="cta-multiverse">{C.multiverse} ↗</Link>
          </div>
          <dl className="mt-10 grid max-w-lg grid-cols-3 gap-px bg-white/[0.06]">
            {C.stats.map(([v, k]) => (
              <div key={k} className="bg-ink px-3 py-3 first:pl-0">
                <dt className="sr-only">{k}</dt>
                <dd className="num font-mono text-2xl font-black text-white">{v}</dd>
                <dd className="mt-0.5 text-[11px] leading-snug text-slate-500">{k}</dd>
              </div>
            ))}
          </dl>
        </div>
        <MultiverseScene lang={lang} />
      </section>

      <section className="section-band">
        <div className="mx-auto max-w-[1400px] px-5 py-16">
          <SectionHead eyebrow={C.howEyebrow} title={C.howTitle} sub={C.howSub} />
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

      <section className="relative mx-auto max-w-[1400px] px-5 py-20">
        <p className="eyebrow">{C.agentsEyebrow}</p>
        <h2 className="mt-3 text-3xl font-black tracking-tight text-white sm:text-4xl">{C.agentsTitle}</h2>
        <p className="mt-3 max-w-2xl text-[14px] leading-relaxed text-slate-400">{C.agentsSub}</p>
        <AgentRelay C={C} />
      </section>

      <section className="section-band">
        <div className="mx-auto max-w-[1400px] px-5 py-16">
          <SectionHead eyebrow={C.compareEyebrow} title={C.compareTitle} sub={C.compareSub} />
          <div className="relative mt-10 grid gap-4 md:grid-cols-2">
            {[
              { label: C.actualMatch, caption: C.actualCaption, d: SHOT_PATH, tone: "#f8fafc", on: false },
              { label: C.yourAlt, caption: C.altCaption, d: PASS_PATH, tone: "#d4ee8f", on: true },
            ].map((p) => (
              <figure key={p.label} className="glass p-2">
                <div className="relative">
                  <span className={`absolute left-2 top-2 z-10 px-2 py-0.5 text-[11px] font-bold ${p.on ? "bg-leaf-500 text-white" : "bg-slate-950/85 text-white ring-1 ring-white/15"}`}>{p.label}</span>
                  <MiniPitch path={p.d} tone={p.tone} animKey={playKey} view="-1 12 70 34" dot={0.85} />
                </div>
                <figcaption className="flex items-center gap-3 px-1 pb-1 pt-2.5">
                  <button type="button" onClick={() => setPlayKey((n) => n + 1)} aria-label={C.play}
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

      <section className="relative mx-auto max-w-[1400px] px-5 pb-16 pt-10">
        <div className="frame relative overflow-hidden px-6 py-14 text-center sm:px-12">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(600px_260px_at_50%_0%,rgba(95,156,94,0.22),transparent_70%)]" aria-hidden />
          <h2 className="relative text-3xl font-black tracking-tight text-white sm:text-5xl">{C.ctaTitle}</h2>
          <p className="relative mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-slate-400">{C.ctaBody}</p>
          <div className="relative mt-8 flex flex-wrap justify-center gap-3">
            <Link href={`${APP}&view=multiverse`} className="btn btn-primary px-6 py-3 text-sm">{C.multiverse} ↗</Link>
            <Link href={APP} className="btn px-6 py-3 text-sm">{C.live}</Link>
          </div>
        </div>
        <p className="mt-6 text-center text-[11px] text-slate-600">{C.note}</p>
      </section>
    </div>
  );
}

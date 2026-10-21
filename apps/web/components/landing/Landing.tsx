"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import BrandMark from "../BrandMark";

type Lang = "en" | "nl";

const COPY = {
  en: {
    eyebrow: "Counterfactual football intelligence",
    title: ["Every decision", "creates another game."],
    sub: "PARALLEL freezes the moment a player decides, plays every option forward hundreds of times and lets a team of agents explain which future was more promising, with the evidence on the table.",
    live: "Watch the live match",
    multiverse: "Enter the Multiverse",
    open: "Open app",
    stats: [
      ["200", "simulations per option"],
      ["5", "agents, one verified answer"],
      ["3", "viewer modes, EN and NL"],
    ],
    howEyebrow: "How it works",
    howTitle: "One moment. Several futures.",
    steps: [
      ["Freeze", "The match stops at the decision. Positions, pressure and passing lanes are captured exactly as they were."],
      ["Branch", "Every realistic alternative is played forward with an explicit simulation model, hundreds of times each."],
      ["Verify", "A verification agent checks every claim against the numbers before anything reaches the screen."],
    ],
    agentsEyebrow: "The agent team",
    agentsTitle: "Five specialists, one pipeline.",
    agents: [
      ["Decision", "spots the moment that mattered"],
      ["Strategy", "proposes the realistic options"],
      ["Simulation", "plays each option forward"],
      ["Verification", "rejects claims the data does not support"],
      ["Explanation", "tells the story for fans, analysts or broadcast"],
    ],
    ctaTitle: "Take the decision yourself.",
    ctaBody: "Pick a moment, choose your own pass or shot, and watch the defence respond in a branch of the match that never happened.",
    labels: { actual: "Actual · shoot", alt1: "Pass · model favours", alt2: "Through ball" },
    note: "Synthetic matches with fictional teams and players. Simulated outcomes are model estimates, not what would have happened.",
  },
  nl: {
    eyebrow: "Contrafactische voetbalintelligentie",
    title: ["Elke beslissing", "creëert een andere wedstrijd."],
    sub: "PARALLEL bevriest het moment waarop een speler beslist, speelt elke optie honderden keren vooruit en laat een team van agents uitleggen welke toekomst kansrijker was, met het bewijs op tafel.",
    live: "Bekijk de live wedstrijd",
    multiverse: "Betreed het Multiverse",
    open: "Open app",
    stats: [
      ["200", "simulaties per optie"],
      ["5", "agents, één geverifieerd antwoord"],
      ["3", "kijkmodi, EN en NL"],
    ],
    howEyebrow: "Hoe het werkt",
    howTitle: "Eén moment. Meerdere toekomsten.",
    steps: [
      ["Bevriezen", "De wedstrijd stopt bij de beslissing. Posities, druk en passlijnen worden exact vastgelegd."],
      ["Vertakken", "Elk realistisch alternatief wordt met een expliciet simulatiemodel honderden keren vooruitgespeeld."],
      ["Verifiëren", "Een verificatie-agent toetst elke bewering aan de cijfers voordat er iets in beeld komt."],
    ],
    agentsEyebrow: "Het agentteam",
    agentsTitle: "Vijf specialisten, één pijplijn.",
    agents: [
      ["Decision", "vindt het moment dat ertoe deed"],
      ["Strategy", "stelt de realistische opties voor"],
      ["Simulation", "speelt elke optie vooruit"],
      ["Verification", "verwerpt claims die de data niet steunt"],
      ["Explanation", "vertelt het verhaal voor fans, analisten of omroep"],
    ],
    ctaTitle: "Neem de beslissing zelf.",
    ctaBody: "Kies een moment, bepaal je eigen pass of schot en zie de verdediging reageren in een tak van de wedstrijd die nooit heeft plaatsgevonden.",
    labels: { actual: "Echt · schot", alt1: "Pass · model kiest", alt2: "Steekpass" },
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
        <BranchLayer z={230} d={`M ${DECISION[0]} ${DECISION[1]} L 18 50 Q 10 46 6 38`} end={[6, 38]} label={`${L.alt2} · 0.9%`} tone="#cfe2b4" delay={1.2} />
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

export default function Landing() {
  const [lang, setLang] = useState<Lang>("en");
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
    <div className="landing min-h-screen overflow-x-hidden">
      <header className="relative z-20 mx-auto flex max-w-[1400px] items-center gap-4 px-5 py-4">
        <div className="flex items-center gap-2">
          <BrandMark size={30} id="land" />
          <span className="text-[15px] font-black tracking-[0.32em] text-white">PARALLEL</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div role="radiogroup" aria-label="Language" className="flex rounded-sm bg-white/[0.04] p-0.5">
            {(["en", "nl"] as const).map((l) => (
              <button key={l} type="button" role="radio" aria-checked={lang === l} onClick={() => setLang(l)} className="tab">{l.toUpperCase()}</button>
            ))}
          </div>
          <Link href={APP} className="btn whitespace-nowrap">{C.open} →</Link>
        </div>
      </header>

      <section className="relative mx-auto grid max-w-[1400px] items-center gap-6 px-5 pb-10 pt-4 lg:min-h-[calc(100vh-72px)] lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="relative z-10 max-w-xl animate-rise">
          <p className="eyebrow">{C.eyebrow}</p>
          <h1 className="mt-4 text-[clamp(2.4rem,4.8vw,4.2rem)] font-black leading-[0.95] tracking-tight text-white">
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

      <section className="relative mx-auto max-w-[1400px] px-5 py-20">
        <p className="eyebrow">{C.howEyebrow}</p>
        <h2 className="mt-3 text-3xl font-black tracking-tight text-white sm:text-4xl">{C.howTitle}</h2>
        <div className="mt-10 grid gap-5 md:grid-cols-3 [perspective:1200px]">
          {C.steps.map(([title, body], i) => (
            <article key={title} className="card3d glass p-6">
              <span className="digit" aria-hidden>{String(i + 1).padStart(2, "0")}</span>
              <h3 className="mt-6 text-xl font-black text-white">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="relative mx-auto max-w-[1400px] px-5 py-20">
        <p className="eyebrow">{C.agentsEyebrow}</p>
        <h2 className="mt-3 text-3xl font-black tracking-tight text-white sm:text-4xl">{C.agentsTitle}</h2>
        <ol className="relative mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-5">
          <span className="absolute left-0 right-0 top-[44px] hidden h-px bg-gradient-to-r from-transparent via-leaf-400/40 to-transparent lg:block" aria-hidden />
          {C.agents.map(([name, role], i) => (
            <li key={name} className="relative flex flex-col items-center text-center">
              <Cube label={name} i={i} />
              <span className="mt-6 text-sm font-black text-white">{name} Agent</span>
              <span className="mt-1 max-w-[16rem] text-[12px] leading-snug text-slate-500">{role}</span>
            </li>
          ))}
        </ol>
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

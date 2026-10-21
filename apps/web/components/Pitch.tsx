"use client";

import type { MatchInfo } from "@parallel/contracts";
import type { ReactNode } from "react";
import type { RenderFrame } from "@/lib/frames";

export interface Arrow {
  id: string;
  from: [number, number];
  to: [number, number];
  kind: "actual" | "selected" | "alternative" | "defense" | "recommended";
  label: string;
  rank?: number;
}

export interface Ring {
  x: number;
  y: number;
  r: number;
}

export interface PitchProps {
  match: MatchInfo;
  frame: RenderFrame | null;
  highlightId?: string | null;
  arrows?: Arrow[];
  trail?: [number, number][];
  ghostTrail?: [number, number][];
  rings?: Ring[];
  lanes?: { from: [number, number]; to: [number, number]; quality: number }[];
  dimmed?: boolean;
  tint?: "observed" | "simulated" | "snapshot";
  onArrowClick?: (id: string) => void;
  onPlayerClick?: (playerId: string) => void;
  onPitchClick?: (x: number, y: number) => void;
  selectableIds?: string[];
  marker?: { x: number; y: number; ok: boolean } | null;
  ariaLabel: string;
  children?: ReactNode;
}

const L = 105;
const W = 68;

function Markings() {
  const line = { stroke: "rgba(255,255,255,0.55)", strokeWidth: 0.18, fill: "none" } as const;
  const box = (x: number, w: number, h: number) => <rect x={x} y={(W - h) / 2} width={w} height={h} {...line} />;
  return (
    <g>
      <rect x={0} y={0} width={L} height={W} {...line} />
      <line x1={L / 2} y1={0} x2={L / 2} y2={W} {...line} />
      <circle cx={L / 2} cy={W / 2} r={9.15} {...line} />
      <circle cx={L / 2} cy={W / 2} r={0.3} fill="rgba(255,255,255,0.7)" />
      {box(0, 16.5, 40.32)}
      {box(L - 16.5, 16.5, 40.32)}
      {box(0, 5.5, 18.32)}
      {box(L - 5.5, 5.5, 18.32)}
      <circle cx={11} cy={W / 2} r={0.25} fill="rgba(255,255,255,0.7)" />
      <circle cx={L - 11} cy={W / 2} r={0.25} fill="rgba(255,255,255,0.7)" />
      <path d={`M ${16.5} ${W / 2 - 7.3} A 9.15 9.15 0 0 1 ${16.5} ${W / 2 + 7.3}`} {...line} />
      <path d={`M ${L - 16.5} ${W / 2 - 7.3} A 9.15 9.15 0 0 0 ${L - 16.5} ${W / 2 + 7.3}`} {...line} />
      <rect x={-1.8} y={W / 2 - 3.66} width={1.8} height={7.32} {...line} />
      <rect x={L} y={W / 2 - 3.66} width={1.8} height={7.32} {...line} />
    </g>
  );
}

function ArrowShape({ a, onClick }: { a: Arrow; onClick?: (id: string) => void }) {
  const color = a.kind === "actual" ? "#f8fafc" : a.kind === "selected" ? "#d4ee8f" : a.kind === "defense" ? "#f97316"
    : a.kind === "recommended" ? "#34d399" : "#cfe2b4";
  const dash = a.kind === "actual" ? "1.2 0.8" : a.kind === "alternative" ? "0.6 0.6" : a.kind === "defense" ? "0.9 0.5" : undefined;
  const [x1, y1] = a.from;
  const [x2, y2] = a.to;
  const ang = Math.atan2(y2 - y1, x2 - x1);
  const hx = x2 - Math.cos(ang) * 1.6;
  const hy = y2 - Math.sin(ang) * 1.6;
  const left = [hx + Math.cos(ang + Math.PI / 2) * 0.8, hy + Math.sin(ang + Math.PI / 2) * 0.8];
  const right = [hx + Math.cos(ang - Math.PI / 2) * 0.8, hy + Math.sin(ang - Math.PI / 2) * 0.8];
  // Labels sit 62% along the arrow, nudged sideways per rank so neighbouring labels do not collide.
  const side = ((a.rank ?? 1) % 2 === 0 ? 1 : -1) * (1.2 + (a.rank ?? 1) * 0.35);
  const mx = x1 + (x2 - x1) * 0.62 + Math.cos(ang + Math.PI / 2) * side;
  const my = y1 + (y2 - y1) * 0.62 + Math.sin(ang + Math.PI / 2) * side;
  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={a.label}
      className="cursor-pointer focus:outline-none"
      onClick={() => onClick?.(a.id)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick?.(a.id)}
    >
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth={3} />
      <line x1={x1} y1={y1} x2={hx} y2={hy} stroke={color} strokeWidth={a.kind === "selected" ? 0.55 : 0.38}
        strokeDasharray={dash} opacity={a.kind === "alternative" ? 0.85 : 1} />
      <polygon points={`${x2},${y2} ${left[0]},${left[1]} ${right[0]},${right[1]}`} fill={color} />
      <g transform={`translate(${mx},${my - 1.6})`}>
        <rect x={-0.2} y={-1.25} width={a.label.length * 0.62 + 1.4} height={1.9} rx={0.12}
          fill="rgba(2,6,23,0.85)" stroke={color} strokeWidth={0.1} />
        <text x={0.5} y={0.15} fontSize={1.15} fill={color} fontWeight={600}>
          {a.rank != null ? `${a.rank}. ` : ""}{a.label}
        </text>
      </g>
    </g>
  );
}

export default function Pitch(p: PitchProps) {
  const home = p.match.home;
  const away = p.match.away;
  const teamOf = new Map(p.match.players.map((pl) => [pl.player_id, pl]));
  const frame = p.frame;
  const tintStroke = p.tint === "simulated" ? "#d4ee8f" : p.tint === "snapshot" ? "#cfe2b4" : "transparent";
  return (
    <svg viewBox={`-3 -3 ${L + 6} ${W + 6}`} className={`block h-auto w-full select-none ${p.onPitchClick ? "cursor-crosshair" : ""}`}
      role="img" aria-label={p.ariaLabel}
      onClick={(e) => {
        if (!p.onPitchClick) return;
        const svg = e.currentTarget;
        const pt = svg.createSVGPoint();
        pt.x = e.clientX;
        pt.y = e.clientY;
        const m = svg.getScreenCTM();
        if (!m) return;
        const loc = pt.matrixTransform(m.inverse());
        if (loc.x >= 0 && loc.x <= L && loc.y >= 0 && loc.y <= W) p.onPitchClick(loc.x, loc.y);
      }}>
      <defs>
        <pattern id="stripes" width={10.5} height={W} patternUnits="userSpaceOnUse">
          <rect width={5.25} height={W} fill="#164730" />
          <rect x={5.25} width={5.25} height={W} fill="#123f2a" />
        </pattern>
        <radialGradient id="vignette" cx="50%" cy="50%" r="75%">
          <stop offset="60%" stopColor="rgba(0,0,0,0)" />
          <stop offset="100%" stopColor="rgba(0,0,0,0.45)" />
        </radialGradient>
      </defs>
      <rect x={-3} y={-3} width={L + 6} height={W + 6} fill="#0a2419" />
      <rect x={0} y={0} width={L} height={W} fill="url(#stripes)" />
      <rect x={0} y={0} width={L} height={W} fill="url(#vignette)" />
      <rect x={-2.6} y={-2.6} width={L + 5.2} height={W + 5.2} fill="none" stroke={tintStroke} strokeWidth={0.5} />
      <Markings />
      {p.lanes?.map((ln, i) => (
        <line key={`lane-${i}`} x1={ln.from[0]} y1={ln.from[1]} x2={ln.to[0]} y2={ln.to[1]}
          stroke={ln.quality > 0.7 ? "#22c55e" : ln.quality > 0.4 ? "#eab308" : "#ef4444"} strokeWidth={0.25}
          opacity={0.6} strokeDasharray="0.4 0.4" />
      ))}
      {p.rings?.map((r, i) => (
        <circle key={`ring-${i}`} cx={r.x} cy={r.y} r={r.r} fill="rgba(239,68,68,0.06)" stroke="rgba(239,68,68,0.6)"
          strokeWidth={0.15} strokeDasharray="0.5 0.4" />
      ))}
      {p.ghostTrail && p.ghostTrail.length > 1 && (
        <polyline points={p.ghostTrail.map((q) => q.join(",")).join(" ")} fill="none" stroke="rgba(248,250,252,0.35)"
          strokeWidth={0.3} strokeDasharray="0.6 0.6" />
      )}
      {p.trail && p.trail.length > 1 && (
        <polyline points={p.trail.map((q) => q.join(",")).join(" ")} fill="none" stroke="#8fca7c" strokeWidth={0.4}
          strokeLinecap="round" opacity={0.9} />
      )}
      <g opacity={p.dimmed ? 0.55 : 1}>
        {frame &&
          Object.entries(frame.players).map(([id, [x, y]]) => {
            const pl = teamOf.get(id);
            if (!pl) return null;
            const isHome = pl.team_id === home.team_id;
            const fill = isHome ? home.color_primary : away.color_primary;
            const hl = id === p.highlightId || id === frame.possessor_id;
            const selectable = p.selectableIds?.includes(id);
            return (
              <g key={id} transform={`translate(${x},${y})`}
                {...(selectable ? {
                  role: "button", tabIndex: 0, "aria-label": `Select ${pl.name ?? id}`, className: "cursor-pointer",
                  "data-testid": `player-${id}`,
                  onClick: (ev: React.MouseEvent) => { ev.stopPropagation(); p.onPlayerClick?.(id); },
                  onKeyDown: (ev: React.KeyboardEvent) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); p.onPlayerClick?.(id); } },
                } : {})}>
                {selectable && <circle r={2.1} fill="rgba(52,211,153,0.12)" stroke="#34d399" strokeWidth={0.18} strokeDasharray="0.5 0.4" />}
                {hl && <circle r={2.2} fill="none" stroke="#f8fafc" strokeWidth={0.22} opacity={0.9} />}
                <circle r={1.25} fill={fill} stroke={pl.role === "GK" ? "#f8fafc" : "#020617"} strokeWidth={0.22} />
                <text y={0.42} fontSize={1.15} textAnchor="middle" fontWeight={700} fill={isHome ? "#04263b" : "#2a1704"}>
                  {pl.shirt_number}
                </text>
              </g>
            );
          })}
        {frame && (
          <g>
            <ellipse cx={frame.ball[0] + frame.ball[2] * 0.4} cy={frame.ball[1] + frame.ball[2] * 0.4} rx={0.6} ry={0.35}
              fill="rgba(0,0,0,0.45)" />
            <circle cx={frame.ball[0]} cy={frame.ball[1] - frame.ball[2] * 0.35} r={0.55 + frame.ball[2] * 0.08}
              fill="#f8fafc" stroke="#0f172a" strokeWidth={0.12} />
          </g>
        )}
      </g>
      {p.arrows?.map((a) => <ArrowShape key={a.id} a={a} onClick={p.onArrowClick} />)}
      {p.marker && (
        <g transform={`translate(${p.marker.x},${p.marker.y})`} pointerEvents="none">
          <circle r={1.6} fill="none" stroke={p.marker.ok ? "#34d399" : "#ef4444"} strokeWidth={0.35} />
          <path d="M -1 -1 L 1 1 M -1 1 L 1 -1" stroke={p.marker.ok ? "#34d399" : "#ef4444"} strokeWidth={0.3} />
        </g>
      )}
      {p.children}
    </svg>
  );
}

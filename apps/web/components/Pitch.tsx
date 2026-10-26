"use client";

import type { MatchInfo } from "@offscript/contracts";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { directionStyle, type Motion } from "@/lib/pitchDirections";
import type { RenderFrame } from "@/lib/frames";

export interface Arrow {
  id: string;
  from: [number, number];
  to: [number, number];
  kind: "actual" | "selected" | "alternative" | "defense" | "recommended";
  label: string;
  rank?: number;
  motion?: Motion;
  badge?: string;
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

const labelText = (a: Arrow) => a.badge ?? `${a.rank != null ? `${a.rank}. ` : ""}${a.label}`;
const labelWidth = (a: Arrow, scale = 1) => a.badge ? Math.max(3.2, a.badge.length * 1.1 + 1.8) * scale : labelText(a).length * 0.72 + 1.6;
const labelHeight = (a: Arrow, scale = 1) => a.badge ? 3.2 * scale : 2.5;
type Box = { x: number; y: number; w: number; h: number };

/** Slab intersection keeps labels clear of every route, including a neighbouring pass. */
function crossesBox(a: Arrow, b: Box): boolean {
  let lo = 0, hi = 1;
  for (const [start, end, min, max] of [[a.from[0], a.to[0], b.x - .5, b.x + b.w + .5],
    [a.from[1], a.to[1], b.y - .5, b.y + b.h + .5]]) {
    const d = end - start;
    if (Math.abs(d) < .001) { if (start < min || start > max) return false; }
    else { const t1 = (min - start) / d, t2 = (max - start) / d; lo = Math.max(lo, Math.min(t1, t2)); hi = Math.min(hi, Math.max(t1, t2)); }
    if (lo > hi) return false;
  }
  return true;
}

/**
 * Places every arrow label without overlaps: candidates along the arrow and on either side, best-ranked
 * arrow first, first free spot that stays on the pitch wins. Returns each label's top-left corner.
 */
export function placeLabels(arrows: Arrow[], scale = 1, blocked: Box[] = []): Map<string, [number, number]> {
  const placed: Box[] = [...blocked];
  const out = new Map<string, [number, number]>();
  const hits = (b: Box) => placed.some((o) => b.x < o.x + o.w + 0.3 && o.x < b.x + b.w + 0.3 && b.y < o.y + o.h + 0.3 && o.y < b.y + b.h + 0.3);
  const order = [...arrows].sort((p, q) => (p.rank ?? 99) - (q.rank ?? 99));
  for (const a of order) {
    const [x1, y1] = a.from;
    const [x2, y2] = a.to;
    const ang = Math.atan2(y2 - y1, x2 - x1);
    const w = labelWidth(a, scale);
    const h = labelHeight(a, scale);
    let pick: Box | null = null;
    for (const t of a.badge ? [1, .85, .65] : [0.62, 0.8, 0.45, 0.95, 0.3]) {
      for (const off of a.badge ? [4, -4, 6, -6, 9, -9, 12, -12] : [3.4, -3.4, 5, -5, 8, -8]) {
        const mx = x1 + (x2 - x1) * t + Math.cos(ang + Math.PI / 2) * off;
        const my = y1 + (y2 - y1) * t + Math.sin(ang + Math.PI / 2) * off;
        const b = { x: mx - w / 2, y: my - h / 2, w, h };
        if (b.x < -2.5 || b.x + b.w > 107.5 || b.y < -2.5 || b.y + b.h > 70.5) continue;
        if (!hits(b) && !arrows.some((route) => crossesBox(route, b))) { pick = b; break; }
      }
      if (pick) break;
    }
    if (!pick) {
      // A control or outcome overlay may occupy the nearby positions. Find the
      // nearest clear location on the pitch instead of stacking outside its edge.
      let nearest = Infinity;
      for (let y = 0; y <= W - h; y += 2) for (let x = 0; x <= L - w; x += 2) {
        const b = { x, y, w, h }, distance = Math.hypot(x + w / 2 - x2, y + h / 2 - y2);
        if (distance < nearest && !hits(b) && !arrows.some((route) => crossesBox(route, b))) { pick = b; nearest = distance; }
      }
      pick ??= { x: Math.min(L - w, Math.max(0, x2 - w / 2)), y: Math.min(W - h, Math.max(0, y2 - h / 2)), w, h };
    }
    placed.push(pick);
    out.set(a.id, [pick.x, pick.y]);
  }
  return out;
}

function ArrowShape({ a, onClick, labelAt, scale }: { a: Arrow; onClick?: (id: string) => void; labelAt?: [number, number]; scale: number }) {
  const { color, dash } = directionStyle(a.kind, a.motion);
  const [x1, y1] = a.from;
  const [x2, y2] = a.to;
  const ang = Math.atan2(y2 - y1, x2 - x1);
  const head = Math.min(2.6, Math.hypot(x2 - x1, y2 - y1) * 0.4);
  const hx = x2 - Math.cos(ang) * head;
  const hy = y2 - Math.sin(ang) * head;
  const left = [hx + Math.cos(ang + Math.PI / 2) * head * 0.48, hy + Math.sin(ang + Math.PI / 2) * head * 0.48];
  const right = [hx + Math.cos(ang - Math.PI / 2) * head * 0.48, hy + Math.sin(ang - Math.PI / 2) * head * 0.48];
  // Label position comes from placeLabels (no overlaps); a lone arrow falls back to 62% along it.
  const [lx, ly] = labelAt ?? [x1 + (x2 - x1) * 0.62 - labelWidth(a) / 2, y1 + (y2 - y1) * 0.62 - 2.6];
  return (
    <g
      role={onClick ? "button" : "img"}
      tabIndex={onClick ? 0 : undefined}
      aria-label={a.label}
      data-testid="pitch-action-arrow" data-motion={a.motion} data-kind={a.kind}
      className={onClick ? "pitch-action-arrow cursor-pointer" : "pitch-action-arrow pointer-events-none"}
      onClick={(e) => { if (onClick) { e.stopPropagation(); onClick(a.id); } }}
      onKeyDown={(e) => { if (onClick && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); e.stopPropagation(); onClick(a.id); } }}
    >
      <title>{a.label}: {a.motion ?? "action"} direction</title>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth={4} />
      <line x1={x1} y1={y1} x2={hx} y2={hy} stroke="#061e13" strokeWidth={1.5} opacity={0.85} />
      <line x1={x1} y1={y1} x2={hx} y2={hy} stroke={color} strokeWidth={a.kind === "selected" ? 0.75 : 0.55}
        strokeLinecap="round" strokeDasharray={dash?.join(" ")} />
      <circle cx={x1} cy={y1} r={0.65} fill={color} stroke="#061e13" strokeWidth={0.22} />
      <circle cx={x2} cy={y2} r={1.7} fill="none" stroke={color} strokeWidth={0.22} opacity={0.65} />
      <polygon points={`${x2},${y2} ${left[0]},${left[1]} ${right[0]},${right[1]}`} fill={color} stroke="#061e13" strokeWidth={0.15} />
      {Math.hypot(x2 - x1, y2 - y1) > 12 && [0.35, 0.65].map((t) => (
        <path key={t} d="M -0.8 -0.8 L 0 0 L -0.8 0.8" transform={`translate(${x1 + (x2 - x1) * t},${y1 + (y2 - y1) * t}) rotate(${ang * 180 / Math.PI})`}
          fill="none" stroke={color} strokeWidth={0.4} strokeLinecap="round" strokeLinejoin="round" />
      ))}
      {onClick && <rect x={lx} y={ly} width={labelWidth(a, scale)} height={labelHeight(a, scale)} fill="transparent" />}
    </g>
  );
}

function ArrowLabel({ a, at, scale }: { a: Arrow; at: [number, number]; scale: number }) {
  const { color } = directionStyle(a.kind, a.motion);
  return (
    <g transform={`translate(${at[0]},${at[1]})`} aria-hidden="true" pointerEvents="none">
      <rect width={labelWidth(a, scale)} height={labelHeight(a, scale)} rx={a.badge ? .4 * scale : .12} fill="#07160f" stroke={color} strokeWidth={a.badge ? .2 * scale : .1} />
      <text x={a.badge ? labelWidth(a, scale) / 2 : .8} y={a.badge ? 2.2 * scale : 1.75} textAnchor={a.badge ? "middle" : undefined}
        fontSize={a.badge ? 1.8 * scale : 1.35} fill={color} fontWeight={700}>{labelText(a)}</text>
    </g>
  );
}

export default function Pitch(p: PitchProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [badgeScale, setBadgeScale] = useState(1);
  const [labelObstacles, setLabelObstacles] = useState<Box[]>([]);
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || typeof ResizeObserver === "undefined") return;
    const stage = svg.closest("[data-pitch-stage]");
    const update = () => {
      const rect = svg.getBoundingClientRect(), px = rect.width / (L + 6);
      if (px <= 0) return;
      setBadgeScale(Math.max(1, 22 / (px * 3.2)));
      const boxes = Array.from(stage?.querySelectorAll("[data-pitch-overlay]") ?? []).flatMap((el) => {
        const r = el.getBoundingClientRect();
        return r.width && r.height ? [{ x: (r.left - rect.left) / px - 3, y: (r.top - rect.top) / px - 3, w: r.width / px, h: r.height / px }] : [];
      });
      setLabelObstacles((old) => JSON.stringify(old) === JSON.stringify(boxes) ? old : boxes);
    };
    const observer = new ResizeObserver(update);
    const observe = () => {
      observer.disconnect();
      observer.observe(svg);
      stage?.querySelectorAll("[data-pitch-overlay]").forEach((el) => observer.observe(el));
      update();
    };
    const mutations = new MutationObserver(observe);
    if (stage) mutations.observe(stage, { childList: true, subtree: true });
    observe();
    return () => { observer.disconnect(); mutations.disconnect(); };
  }, []);
  const home = p.match.home;
  const away = p.match.away;
  const teamOf = new Map(p.match.players.map((pl) => [pl.player_id, pl]));
  const frame = p.frame;
  const tintStroke = p.tint === "simulated" ? "#d4ee8f" : p.tint === "snapshot" ? "#cfe2b4" : "transparent";
  return (
    <svg ref={svgRef} viewBox={`-3 -3 ${L + 6} ${W + 6}`} className={`block h-auto w-full select-none ${p.onPitchClick ? "cursor-crosshair" : ""}`}
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
      {(() => {
        const at = placeLabels(p.arrows ?? [], badgeScale, labelObstacles);
        return <>
          <g data-testid="pitch-routes">{p.arrows?.map((a) => <ArrowShape key={a.id} a={a} onClick={p.onArrowClick} labelAt={at.get(a.id)} scale={badgeScale} />)}</g>
          {/* Paint every label after every route so a later arrow cannot cross its text. */}
          <g pointerEvents="none" aria-hidden="true">{p.arrows?.filter((a) => a.badge).map((a) => {
            const [x, y] = at.get(a.id)!;
            return <line key={a.id} x1={a.to[0]} y1={a.to[1]} x2={x + labelWidth(a, badgeScale) / 2} y2={y + labelHeight(a, badgeScale) / 2}
              stroke={directionStyle(a.kind, a.motion).color} strokeWidth={.18} />;
          })}</g>
          <g data-testid="pitch-route-labels">{p.arrows?.map((a) => <ArrowLabel key={a.id} a={a} at={at.get(a.id)!} scale={badgeScale} />)}</g>
        </>;
      })()}
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

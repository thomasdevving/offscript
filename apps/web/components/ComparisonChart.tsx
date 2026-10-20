"use client";

import type { ActionResult, CandidateAction, Language } from "@parallel/contracts";
import { cleanLabel, pct } from "@/lib/format";

/** Horizontal bars of P(goal within horizon) with 95% Wilson whiskers (custom SVG, no chart library). */
export default function ComparisonChart(props: {
  candidates: CandidateAction[];
  results: ActionResult[];
  selected: string | null;
  lang: Language;
  metric?: "p_goal" | "p_shot" | "p_turnover";
}) {
  const metric = props.metric ?? "p_goal";
  const res = new Map(props.results.map((r) => [r.action_id, r]));
  const rows = props.candidates.filter((c) => res.has(c.action_id));
  const maxV = Math.max(0.05, ...rows.map((c) => res.get(c.action_id)![metric].ci95_high)) * 1.15;
  const W = 300;
  const rowH = 26;
  const labelW = 120;
  const H = rows.length * rowH + 18;
  const x = (v: number) => labelW + (v / maxV) * (W - labelW - 44);
  const ticks = [0, maxV / 2, maxV].map((v) => Math.round(v * 1000) / 1000);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
      aria-label={`Comparison chart of ${metric} with 95% intervals`}>
      {ticks.map((tk) => (
        <g key={tk}>
          <line x1={x(tk)} x2={x(tk)} y1={0} y2={H - 14} stroke="#1e293b" />
          <text x={x(tk)} y={H - 3} fontSize={8} textAnchor="middle" fill="#64748b">{pct(tk, props.lang, 0)}</text>
        </g>
      ))}
      {rows.map((c, i) => {
        const r = res.get(c.action_id)!;
        const est = r[metric];
        const y = i * rowH + 4;
        const color = c.action_id === props.selected ? "#3b82f6" : c.is_actual ? "#e2e8f0" : "#a78bfa";
        return (
          <g key={c.action_id}>
            <text x={labelW - 6} y={y + 12} fontSize={9} textAnchor="end" fill="#cbd5e1">
              {cleanLabel(c.label).slice(0, 24)}{c.is_actual ? " *" : ""}
            </text>
            <rect x={labelW} y={y + 3} width={Math.max(1, x(est.value) - labelW)} height={12} rx={2} fill={color} opacity={0.85}
              {...(c.is_actual ? { stroke: "#f8fafc", strokeDasharray: "2 1.5" } : {})} />
            <line x1={x(est.ci95_low)} x2={x(est.ci95_high)} y1={y + 9} y2={y + 9} stroke="#f8fafc" strokeWidth={1.2} />
            <line x1={x(est.ci95_low)} x2={x(est.ci95_low)} y1={y + 5} y2={y + 13} stroke="#f8fafc" strokeWidth={1.2} />
            <line x1={x(est.ci95_high)} x2={x(est.ci95_high)} y1={y + 5} y2={y + 13} stroke="#f8fafc" strokeWidth={1.2} />
            <text x={x(est.ci95_high) + 4} y={y + 12} fontSize={9} fill="#f8fafc" fontFamily="monospace">{pct(est.value, props.lang)}</text>
          </g>
        );
      })}
    </svg>
  );
}

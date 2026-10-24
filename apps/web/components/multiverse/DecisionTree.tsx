"use client";

import { clock } from "@/lib/format";
import type { TreeNode } from "@/lib/multiverseApi";
import { mv, useMv } from "@/lib/mvStore";

const COL = 150;
const ROW = 64;
const W = 132;
const H = 48;

function layout(nodes: TreeNode[], rootId: string) {
  const byId = new Map(nodes.map((n) => [n.node_id, n]));
  const pos = new Map<string, { x: number; y: number }>();
  let leaf = 0;
  const visit = (id: string): number => {
    const n = byId.get(id);
    if (!n) return leaf;
    const kids = n.children.filter((c) => byId.has(c));
    let y: number;
    if (!kids.length) {
      y = leaf++;
    } else {
      const ys = kids.map(visit);
      y = (Math.min(...ys) + Math.max(...ys)) / 2;
    }
    pos.set(id, { x: n.depth * COL + 8, y: y * ROW + 8 });
    return y;
  };
  visit(rootId);
  return { pos, rows: Math.max(1, leaf) };
}

function tone(n: TreeNode, selected: boolean): { stroke: string; fill: string } {
  if (selected) return { stroke: "#8fca7c", fill: "rgba(74,129,80,0.25)" };
  if (n.kind === "observed") return { stroke: "#e2e8f0", fill: "rgba(148,163,184,0.12)" };
  if (n.status === "failed") return { stroke: "#ef4444", fill: "rgba(239,68,68,0.12)" };
  if (n.status === "terminal") return { stroke: "#f59e0b", fill: "rgba(245,158,11,0.10)" };
  if (n.kind === "root") return { stroke: "#cfe2b4", fill: "rgba(201,220,162,0.14)" };
  return { stroke: "rgba(148,163,184,0.35)", fill: "rgba(255,255,255,0.04)" };
}

export default function DecisionTree() {
  const tree = useMv((s) => s.tree);
  const selected = useMv((s) => s.selected);
  const job = useMv((s) => s.job);
  if (!tree) return null;
  const { pos, rows } = layout(tree.nodes, tree.root_node_id);
  const maxDepth = Math.max(0, ...tree.nodes.map((n) => n.depth));
  const width = (maxDepth + 1) * COL + 24 + (job ? COL : 0);
  const height = (rows + (job ? 1 : 0)) * ROW + 16;
  const pendingParent = job && ["pending", "running"].includes(job.status) ? job.parent_node_id : null;
  const pp = pendingParent ? pos.get(pendingParent) : null;
  return (
    <div className="overflow-auto" data-testid="decision-tree">
      <svg width={width} height={height} role="tree" aria-label="Multiverse decision tree">
        {tree.nodes.map((n) => {
          const a = n.parent_node_id ? pos.get(n.parent_node_id) : null;
          const b = pos.get(n.node_id);
          if (!a || !b) return null;
          return (
            <path key={`e-${n.node_id}`} d={`M ${a.x + W} ${a.y + H / 2} C ${a.x + W + 14} ${a.y + H / 2}, ${b.x - 14} ${b.y + H / 2}, ${b.x} ${b.y + H / 2}`}
              fill="none" stroke={n.kind === "observed" ? "#94a3b8" : n.node_id === selected ? "#8fca7c" : "#475569"} strokeWidth={n.node_id === selected ? 2 : 1.4}
              strokeDasharray={n.kind === "observed" ? "4 3" : undefined} className="motion-safe:animate-[pop_0.4s_ease-out]" />
          );
        })}
        {pp && (
          <g transform={`translate(${pp.x + COL},${pp.y + ROW})`}>
            <path d={`M ${-COL + W} ${-ROW + H / 2} C ${-10} ${-ROW + H / 2}, -14 ${H / 2}, 0 ${H / 2}`} fill="none" stroke="#8fca7c" strokeDasharray="3 3" />
            <rect width={W} height={H} rx={2} fill="rgba(74,129,80,0.12)" stroke="#8fca7c" strokeDasharray="4 3" className="animate-pulse" />
            <text x={10} y={20} fontSize={11} fill="#dcefd2" fontWeight={700}>Agents planning…</text>
            <text x={10} y={36} fontSize={10} fill="#b6dca6">{job?.progress[job.progress.length - 1] ?? "starting"}</text>
          </g>
        )}
        {tree.nodes.map((n) => {
          const p = pos.get(n.node_id);
          if (!p) return null;
          const sel = n.node_id === selected;
          const t = tone(n, sel);
          const src = n.kind === "observed" ? "ACTUAL" : n.source === "user" ? "USER" : n.source === "attacking_agent" ? "AI" : n.kind === "root" ? "DECISION" : "";
          return (
            <g key={n.node_id} transform={`translate(${p.x},${p.y})`} role="treeitem" aria-selected={sel} tabIndex={0}
              aria-label={`${n.label} ${n.outcome}`} className="cursor-pointer" data-testid={`tree-node-${n.kind}`}
              data-node-id={n.node_id}
              onClick={() => void mv.select(n.node_id, { play: n.kind !== "root" })}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && void mv.select(n.node_id, { play: n.kind !== "root" })}>
              <rect width={W} height={H} rx={2} fill={t.fill} stroke={t.stroke} strokeWidth={sel ? 2 : 1} />
              <rect width={3} height={H} fill={t.stroke} />
              {sel && <rect x={-3} y={-3} width={W + 6} height={H + 6} rx={3} fill="none" stroke="#8fca7c" strokeOpacity={0.25} strokeWidth={4} />}
              <text x={10} y={14} fontSize={9} fill="#94a3b8" fontFamily="monospace">{clock(n.match_clock_ms)} {src}</text>
              <text x={10} y={29} fontSize={11} fill="#f8fafc" fontWeight={700}>{n.label.slice(0, 20)}</text>
              <text x={10} y={42} fontSize={9.5} fill={n.status === "terminal" ? "#fcd34d" : "#c9dca2"}>
                {(n.kind === "root" ? "your move" : n.outcome || n.status).replace(/_/g, " ").slice(0, 18)}
                {n.value_vs_counter != null ? ` · ${(n.value_vs_counter * 100).toFixed(1)}%` : ""}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

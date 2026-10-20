import type { TrackingFrame } from "@parallel/contracts";

export interface RenderFrame {
  t_ms: number;
  ball: [number, number, number];
  players: Record<string, [number, number]>;
  possessor_id: string | null;
}

/** Binary search for the last frame with t <= time. */
export function frameIndexAt(frames: TrackingFrame[], t: number): number {
  let lo = 0;
  let hi = frames.length - 1;
  if (hi < 0) return -1;
  if (t <= frames[0].t_ms) return 0;
  if (t >= frames[hi].t_ms) return hi;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (frames[mid].t_ms <= t) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/** Linear interpolation between neighbouring frames (players and ball). */
export function interpolate(frames: TrackingFrame[], t: number): RenderFrame | null {
  if (!frames.length) return null;
  const i = frameIndexAt(frames, t);
  const a = frames[i];
  const b = frames[Math.min(i + 1, frames.length - 1)];
  const span = b.t_ms - a.t_ms;
  const w = span > 0 ? Math.min(1, Math.max(0, (t - a.t_ms) / span)) : 0;
  const players: Record<string, [number, number]> = {};
  for (const [id, p] of Object.entries(a.players)) {
    const q = (b.players as Record<string, [number, number]>)[id] ?? p;
    players[id] = [p[0] + (q[0] - p[0]) * w, p[1] + (q[1] - p[1]) * w];
  }
  const ball: [number, number, number] = [
    a.ball[0] + (b.ball[0] - a.ball[0]) * w,
    a.ball[1] + (b.ball[1] - a.ball[1]) * w,
    a.ball[2] + (b.ball[2] - a.ball[2]) * w,
  ];
  return { t_ms: t, ball, players, possessor_id: (w < 0.5 ? a.possessor_id : b.possessor_id) ?? null };
}

/** Ball path (for drawing a trajectory line) between two times. */
export function ballPath(frames: TrackingFrame[], from = 0, to = Infinity): [number, number][] {
  return frames.filter((f) => f.t_ms >= from && f.t_ms <= to).map((f) => [f.ball[0], f.ball[1]]);
}

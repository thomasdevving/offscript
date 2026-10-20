import type { TrackingFrame } from "@parallel/contracts";
import { describe, expect, it } from "vitest";
import { ballPath, frameIndexAt, interpolate } from "@/lib/frames";
import { clock, pct, signedPp } from "@/lib/format";
import { dictionaries, eventLabel } from "@/lib/i18n";

const frames: TrackingFrame[] = [
  { t_ms: 0, ball: [10, 10, 0], players: { A: [0, 0] }, possessor_id: "A" },
  { t_ms: 100, ball: [20, 10, 1], players: { A: [1, 0] }, possessor_id: null },
  { t_ms: 200, ball: [30, 10, 0], players: { A: [2, 0] }, possessor_id: null },
];

describe("frames", () => {
  it("finds the frame index by time", () => {
    expect(frameIndexAt(frames, -5)).toBe(0);
    expect(frameIndexAt(frames, 150)).toBe(1);
    expect(frameIndexAt(frames, 999)).toBe(2);
  });

  it("interpolates players and ball linearly", () => {
    const f = interpolate(frames, 50)!;
    expect(f.players.A[0]).toBeCloseTo(0.5);
    expect(f.ball[0]).toBeCloseTo(15);
    expect(f.ball[2]).toBeCloseTo(0.5);
    expect(interpolate([], 0)).toBeNull();
  });

  it("extracts a ball path", () => {
    expect(ballPath(frames, 0, 100)).toEqual([[10, 10], [20, 10]]);
  });
});

describe("format and i18n", () => {
  it("formats percentages per language", () => {
    expect(pct(0.0205)).toBe("2.1%");
    expect(pct(0.0205, "nl")).toBe("2,1%");
    expect(signedPp(0.02)).toBe("+2.0 pp");
    expect(clock(4367000)).toBe("72:47");
  });

  it("has the same keys in English and Dutch", () => {
    const en = Object.keys(dictionaries.en).sort();
    const nl = Object.keys(dictionaries.nl).sort();
    expect(nl).toEqual(en);
    expect(eventLabel("GOAL", "nl")).toBe("DOELPUNT");
  });
});

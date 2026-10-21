import type { Overlay } from "@offscript/contracts";
import { describe, expect, it } from "vitest";
import { activeOverlay } from "@/lib/overlayEngine";

function ov(p: Partial<Overlay>): Overlay {
  return {
    schema_version: "1.0", overlay_id: p.overlay_id ?? "o", type: "decision_comparison", match_id: "m",
    viewer_mode: "casual", language: "en", match_time_ms: 0, sim_time_ms: 1000, duration_ms: 5000, priority: 60,
    headline: "h", narrative: "n", data_fields: [], source_refs: [], verification_status: "verified",
    expires: { on_event_types: ["GOAL"], max_age_ms: null }, render_hint: {}, ...p,
  } as Overlay;
}

describe("activeOverlay", () => {
  it("shows an overlay only within its window", () => {
    const o = ov({});
    expect(activeOverlay([o], 500, "casual", "en", [])).toBeNull();
    expect(activeOverlay([o], 1000, "casual", "en", [])).toBe(o);
    expect(activeOverlay([o], 5999, "casual", "en", [])).toBe(o);
    expect(activeOverlay([o], 6000, "casual", "en", [])).toBeNull();
  });

  it("filters by viewer mode and language", () => {
    const o = ov({ viewer_mode: "analyst", language: "nl" });
    expect(activeOverlay([o], 2000, "casual", "en", [])).toBeNull();
    expect(activeOverlay([o], 2000, "analyst", "nl", [])).toBe(o);
  });

  it("higher priority wins, goals override decision cards", () => {
    const card = ov({ overlay_id: "card", priority: 70 });
    const goal = ov({ overlay_id: "goal", type: "goal", priority: 100, sim_time_ms: 2000,
      expires: { on_event_types: ["MATCH_ENDED"], max_age_ms: 7000 } });
    expect(activeOverlay([card, goal], 2500, "casual", "en", [])?.overlay_id).toBe("goal");
  });

  it("expires early when a listed event happens after it started", () => {
    const card = ov({});
    const events = [{ event_type: "GOAL" as const, sim_time_ms: 3000 }];
    expect(activeOverlay([card], 2500, "casual", "en", events)).toBe(card);
    expect(activeOverlay([card], 3500, "casual", "en", events)).toBeNull();
  });

  it("respects max_age_ms", () => {
    const card = ov({ expires: { on_event_types: [], max_age_ms: 1000 } });
    expect(activeOverlay([card], 1900, "casual", "en", [])).toBe(card);
    expect(activeOverlay([card], 2100, "casual", "en", [])).toBeNull();
  });
});

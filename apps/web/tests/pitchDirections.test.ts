import type { CandidateAction, MatchStateSnapshot } from "@offscript/contracts";
import { describe, expect, it } from "vitest";
import { actionDirection, directionStyle } from "@/lib/pitchDirections";
import { placeLabels, type Arrow } from "@/components/Pitch";

const snapshot = {
  possession_team_id: "home", attack_direction: { home: 1, away: -1 },
  players: [
    { player_id: "h", team_id: "home", x: 70, y: 34 },
    { player_id: "receiver", team_id: "home", x: 85, y: 50 },
    { player_id: "a", team_id: "away", x: 30, y: 34 },
  ],
} as unknown as MatchStateSnapshot;
const action = (changes: Partial<CandidateAction>): CandidateAction => ({
  action_id: "pass", actor_id: "h", action_type: "pass", target_player_id: "receiver",
  initial_state_id: "frozen", is_actual: false, label: "Pass", source: "generator", features: {}, ...changes,
});

describe("action directions", () => {
  it("uses the validated target point for a through pass, rather than the receiver's current position", () => {
    const d = actionDirection(action({ target_x: 95, target_y: 20 }), snapshot)!;
    expect(d.from).toEqual([70, 34]);
    expect(d.to).toEqual([95, 20]);
    expect(d.description).toBe("Forward · 29 m");
    expect(d.angle).toBeLessThan(0);
  });
  it("aims shots at the actor's goal even when the successor state changed possession", () => {
    const d = actionDirection(action({ actor_id: "a", action_type: "shoot" }), snapshot)!;
    expect(d.to).toEqual([0, 34]);
    expect(d.description).toBe("Forward · 30 m");
  });
  it("does not invent a direction for an unknown actor or missing target", () => {
    expect(actionDirection(action({ actor_id: "missing" }), snapshot)).toBeNull();
    expect(actionDirection(action({ target_player_id: "missing" }), snapshot)).toBeNull();
  });
  it("distinguishes pass, dribble, shot and defensive movement without relying on colour alone", () => {
    const patterns = [directionStyle("selected", "pass"), directionStyle("selected", "dribble"),
      directionStyle("selected", "shoot"), directionStyle("defense", "run")].map((s) => String(s.dash));
    expect(new Set(patterns).size).toBe(4);
  });
  it.each([1, 2.5])("keeps markers off neighbouring pass routes at badge scale %s", (scale) => {
    const routes: Arrow[] = [
      { id: "one", from: [20, 34], to: [40, 34], kind: "alternative", label: "Pass one", badge: "1" },
      { id: "two", from: [20, 34], to: [40, 35], kind: "alternative", label: "Pass two", badge: "2" },
    ];
    const labels = placeLabels(routes, scale);
    const size = 3.2 * scale;
    const a = labels.get("one")!, b = labels.get("two")!;
    for (const [x, y] of [a, b]) {
      // Both routes stay in the y=34..35 corridor: neither badge may cover it.
      expect(y + size < 34 || y > 35).toBe(true);
      expect(Math.hypot(x + size / 2 - 40, y + size / 2 - 34)).toBeLessThan(14);
    }
    expect(Math.abs(a[0] - b[0]) >= size || Math.abs(a[1] - b[1]) >= size).toBe(true);
  });
});

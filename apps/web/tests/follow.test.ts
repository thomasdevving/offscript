import type { DecisionPoint, MatchInfo } from "@offscript/contracts";
import { describe, expect, it } from "vitest";
import { activeFollow, decodeFollow, encodeFollow, followLabel, followRelation, pausesFor } from "@/lib/follow";

const match = {
  home: { team_id: "HCF", name: "Harbour City FC" },
  away: { team_id: "NVA", name: "Northvale Athletic" },
  players: [
    { player_id: "H10", team_id: "HCF", name: "Ravi Castellane" },
    { player_id: "H07", team_id: "HCF", name: "Theo Mbeki-Larsen" },
    { player_id: "N04", team_id: "NVA", name: "Dario Kestrel" },
  ],
} as unknown as MatchInfo;
const decision = (actor_id: string) => ({ actor_id }) as DecisionPoint;

describe("follow a team or player", () => {
  it("round-trips the stored choice", () => {
    expect(decodeFollow(encodeFollow({ kind: "player", id: "H10" }))).toEqual({ kind: "player", id: "H10" });
    expect(decodeFollow("")).toBeNull();
    expect(decodeFollow("nonsense")).toBeNull();
  });

  it("changes nothing for fans who follow everyone", () => {
    expect(pausesFor(null, decision("N04"), match)).toBe(true);
    expect(followRelation(null, decision("H10"), match)).toBeNull();
  });

  it("pauses only for the followed team's decisions and marks the opponent's", () => {
    const f = { kind: "team" as const, id: "HCF" };
    expect(pausesFor(f, decision("H10"), match)).toBe(true);
    expect(pausesFor(f, decision("N04"), match)).toBe(false);
    expect(followRelation(f, decision("N04"), match)).toBe("opponent");
    expect(followLabel(f, match)).toBe("Harbour City FC");
  });

  it("follows a single player", () => {
    const f = { kind: "player" as const, id: "H10" };
    expect(followRelation(f, decision("H10"), match)).toBe("player");
    expect(pausesFor(f, decision("H07"), match)).toBe(false);
  });

  it("ignores a choice that is not in this match", () => {
    expect(activeFollow({ kind: "player", id: "X99" }, match)).toBeNull();
    expect(pausesFor({ kind: "team", id: "ZZZ" }, decision("N04"), match)).toBe(true);
  });
});

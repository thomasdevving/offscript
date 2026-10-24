import { describe, expect, it } from "vitest";
import { outcomeLabel, plainCheckIssue } from "@/lib/format";

describe("plain-language check messages", () => {
  it("translates verifier and validation messages", () => {
    expect(plainCheckIssue("broadcaster/en: Unknown evidence references: ['results.alt1.verdict']"))
      .toBe("Broadcast text: cited a source field that does not exist");
    expect(plainCheckIssue("casual/en: Unsupported percentage 19.3% (no matching evidence field)"))
      .toBe("Fan text: a percentage (19.3%) that the simulation never produced");
    expect(plainCheckIssue("PLAYER_NOT_ON_PITCH: H14 is not on the pitch (substitute)")).toBe("H14 is not on the pitch (substitute)");
  });

  it("names simulator outcomes in words", () => {
    expect(outcomeLabel("off_target")).toBe("Off target");
    expect(outcomeLabel("turnover")).toBe("Lost the ball");
  });
});

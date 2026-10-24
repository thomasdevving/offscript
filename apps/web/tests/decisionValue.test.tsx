import type { DecisionValueAggregate, DecisionValueReport, MatchInfo } from "@offscript/contracts";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DecisionValue from "@/components/DecisionValue";
import { headlinePlayer, leftOnTable, oneLiner, pp } from "@/lib/decisionValue";
import { useApp } from "@/lib/store";

const agg = (over: Partial<DecisionValueAggregate>): DecisionValueAggregate => ({
  scope: "player", key: "H10", name: "Ravi Castellane", team_id: "HCF", n_decisions: 4, enough_decisions: true,
  dva_sum: -0.018, dva_sum_ci95_low: -0.032, dva_sum_ci95_high: -0.004, dva_mean: -0.004, dva_mean_ci95_low: -0.008,
  dva_mean_ci95_high: -0.001, clear_misses: 1, ...over,
});

const report: DecisionValueReport = {
  match_id: "m", generated_at: "", metric: "p_goal_within_horizon", horizon_s: 10, min_decisions: 3,
  decisions_detected: 9, decisions_analysed: 7, decisions_pending: 0, decisions: [],
  players: [
    agg({}),
    agg({ key: "H07", name: "Theo Mbeki-Larsen", dva_sum: -0.005, dva_sum_ci95_low: -0.02, dva_sum_ci95_high: 0, n_decisions: 3, clear_misses: 0 }),
    agg({ key: "A09", name: "Leon Varga", team_id: "NVA", n_decisions: 1, enough_decisions: false, dva_sum: null, dva_sum_ci95_low: null,
      dva_sum_ci95_high: null, dva_mean: null, dva_mean_ci95_low: null, dva_mean_ci95_high: null, clear_misses: 0 }),
  ],
  teams: [agg({ scope: "team", key: "HCF", name: "Harbour City FC", n_decisions: 7, dva_sum: -0.023 })],
  match: agg({ scope: "match", key: "m", name: "Harbour City FC v Northvale Athletic", team_id: null, n_decisions: 8, dva_sum: -0.023 }),
  method: "Decision Value Added (DVA) per decision = ...", disclaimer: "Synthetic match with fictional players.",
};

const match = {
  home: { team_id: "HCF", color_primary: "#0af" }, away: { team_id: "NVA", color_primary: "#f50" },
  players: [{ player_id: "H10", short_name: "Castellane" }, { player_id: "H07", short_name: "Mbeki-Larsen" }],
} as unknown as MatchInfo;

describe("decision value text", () => {
  it("formats percentage points and the left-on-the-table interval", () => {
    expect(pp(-0.018)).toBe("-1.8");
    expect(pp(-0.0001)).toBe("0.0");
    expect(pp(0.0125, "nl")).toBe("1,3");
    expect(leftOnTable(report.players[0])).toEqual({ value: "1.8", low: "0.4", high: "3.2" });
    expect(leftOnTable(report.players[2])).toBeNull();
  });

  it("headlines the player who left the most, ignoring small samples", () => {
    expect(headlinePlayer(report)?.key).toBe("H10");
    expect(headlinePlayer({ ...report, players: [report.players[2]] })).toBeNull();
  });

  it("writes one line per viewer mode from the report numbers", () => {
    const names = { H10: "Castellane" };
    expect(oneLiner(report, "broadcaster", "en", names)).toBe(
      "Castellane's choices left 1.8 pp of modelled goal chance on the table this match (95% interval 0.4-3.2 pp, 4 decisions).");
    expect(oneLiner(report, "casual")).toContain("Under our simulation model, Ravi Castellane could have added about 1.8 percentage points");
    expect(oneLiner(report, "analyst")).toContain("DVA -1.8 pp over 4 decisions (95% interval -3.2 to -0.4 pp; mean -0.4 pp per decision; 1 with a clearly better alternative)");
    expect(oneLiner(report, "broadcaster", "nl", names)).toContain("De keuzes van Castellane lieten deze wedstrijd 1,8 pp");
  });

  it("says when the model found no better option, and when there are too few decisions", () => {
    const perfect = { ...report, players: [agg({ dva_sum: 0, dva_sum_ci95_low: -0.01, dva_sum_ci95_high: 0 })] };
    expect(oneLiner(perfect, "broadcaster")).toContain("picked the best available option at all 4 analysed decisions");
    expect(oneLiner({ ...report, players: [report.players[2]] }, "casual")).toBe(
      "Not enough analysed decisions per player yet (minimum 3; 7 of 9 decisions analysed).");
  });
});

describe("DecisionValue view", () => {
  beforeEach(() => {
    useApp.setState({ matchId: "m", match, decisionValue: report, decisionValueLoading: false, decisionValueError: null, mode: "broadcaster", lang: "en" });
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows the one-liner, a per-player table with intervals and 'not enough decisions'", () => {
    render(<DecisionValue />);
    expect(screen.getByTestId("dva-oneliner")).toHaveTextContent("Castellane's choices left 1.8 pp");
    const table = screen.getByTestId("dva-table");
    expect(within(table).getByText("Ravi Castellane").closest("tr")).toHaveTextContent("1.8 pp (0.4–3.2)");
    // Players without a value are folded into one line until expanded.
    expect(within(table).queryByText("Leon Varga")).not.toBeInTheDocument();
    fireEvent.click(within(table).getByTestId("dva-show-thin"));
    expect(within(table).getByText("Leon Varga").closest("tr")).toHaveTextContent("Not enough decisions");
    expect(within(table).getByText("Harbour City FC")).toBeInTheDocument();
    expect(screen.getByText(/7 of 9 detected decisions analysed and verified/)).toBeInTheDocument();
  });

  it("analyst mode shows signed DVA, interval, mean and clear misses", () => {
    useApp.setState({ mode: "analyst" });
    render(<DecisionValue />);
    const row = within(screen.getByTestId("dva-table")).getByText("Ravi Castellane").closest("tr")!;
    expect(row).toHaveTextContent("-1.8");
    expect(row).toHaveTextContent("-3.2 … -0.4");
    expect(row).toHaveTextContent("-0.4");
    expect(screen.getByText("DVA (pp)")).toBeInTheDocument();
  });

  it("compact view leaves out team and match rows", () => {
    render(<DecisionValue compact />);
    expect(screen.queryByText("Harbour City FC")).not.toBeInTheDocument();
  });

  it("offers to analyse the remaining decisions", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ...report, decisions_analysed: 9 }), { status: 202 }));
    render(<DecisionValue />);
    fireEvent.click(screen.getByTestId("dva-analyse-all"));
    await vi.waitFor(() => expect(useApp.getState().decisionValue?.decisions_analysed).toBe(9));
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/matches/m/decision-value/analyze");
    expect(screen.queryByTestId("dva-analyse-all")).not.toBeInTheDocument();
  });
});

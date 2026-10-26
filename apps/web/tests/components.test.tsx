import type { CounterfactualAnalysis, DecisionPoint, MatchInfo } from "@offscript/contracts";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import AnalysisPanel from "@/components/AnalysisPanel";
import ComparisonChart from "@/components/ComparisonChart";
import Pitch from "@/components/Pitch";
import { useApp } from "@/lib/store";

const est = (v: number, n = 200) => ({ value: v, ci95_low: Math.max(0, v - 0.01), ci95_high: v + 0.02, successes: Math.round(v * n), trials: n, method: "wilson" as const });

const decision = {
  decision_point_id: "dp1", match_id: "m", snapshot_id: "s", event_id: "e", actor_id: "H10", actor_name: "Ravi Castellane",
  team_id: "HCF", sim_time_ms: 3000, match_clock_ms: 4367000,
  actual_action: { action_id: "s-actual", action_type: "shoot", actor_id: "H10", initial_state_id: "s", is_actual: true, label: "Shoot (actual)", source: "observed", features: {} },
  actual_outcome: "SHOT_BLOCKED", triggers: ["SHOT_WITH_TEAMMATE_AVAILABLE"],
  features: { distance_to_goal_m: 23, goal_angle_deg: 18, pressure_count_5m: 2, nearest_defender_m: 1.3, open_teammates: 4, forward_options: 2, zone_value: 0.03 },
  candidate_score: 1, source: "detector", analysis_ids: [],
} as unknown as DecisionPoint;

const analysis = {
  analysis_id: "a1", match_id: "m", decision_point_id: "dp1", snapshot_id: "s", correlation_id: "c", status: "verified",
  created_at: "", cached: false, fault_injection: [],
  candidates: [
    decision.actual_action,
    { action_id: "s-pass-H07", action_type: "pass", actor_id: "H10", target_player_id: "H07", target_x: 12, target_y: 20, initial_state_id: "s", is_actual: false, label: "Pass to Mbeki-Larsen", source: "agent", features: { completion_estimate: 0.8 } },
  ],
  simulation: {
    simulation_run_id: "sim", analysis_id: "a1", snapshot_id: "s", simulator_version: "v", status: "completed", partial: false,
    config: { horizon_s: 10, rollouts: 200, seed: 1, simulator_version: "v", common_random_numbers: true, time_budget_s: 20, metric: "p_goal_within_horizon" },
    results: [
      { action_id: "s-actual", n_rollouts: 200, p_goal: est(0), p_shot: est(1), p_turnover: est(0), p_first_action_success: est(0.14), mean_progression_m: 1, outcome_distribution: {}, outcome_counts: {}, representative_rollout: 0, representative_outcome: "blocked", example_rollouts: {}, first_action_detail: {} },
      { action_id: "s-pass-H07", n_rollouts: 200, p_goal: est(0.02), p_shot: est(0.72), p_turnover: est(0.28), p_first_action_success: est(0.75), mean_progression_m: 3, outcome_distribution: {}, outcome_counts: {}, representative_rollout: 4, representative_outcome: "saved", example_rollouts: { saved: 4 }, first_action_detail: {} },
    ],
    comparisons: [{ action_id: "s-pass-H07", baseline_action_id: "s-actual", diff_p_goal: 0.02, diff_ci95_low: 0.001, diff_ci95_high: 0.039, paired: true, verdict: "more_promising", diff_p_shot: 0, diff_p_shot_ci95_low: 0, diff_p_shot_ci95_high: 0, diff_p_turnover: 0, diff_p_turnover_ci95_low: 0, diff_p_turnover_ci95_high: 0, secondary_note: "" }],
    ranking: ["s-pass-H07", "s-actual"], overall_verdict: "more_promising",
  },
  narratives: [
    { narrative_id: "n1", analysis_id: "a1", audience: "casual", language: "en", headline: "Was there a better option?", body: "Under our simulation model, a pass to Mbeki-Larsen led to a goal in 2.0% of 200 simulated continuations.", bullets: [], evidence_refs: [], verification_status: "verified", verification_notes: [], generated_by: "policy-template", is_live_model_output: false, created_at: "" },
    { narrative_id: "n2", analysis_id: "a1", audience: "analyst", language: "en", headline: "73' analysis", body: "Paired rollouts.", bullets: ["Shoot: P(goal) 0.0%"], evidence_refs: [], verification_status: "verified", verification_notes: [], generated_by: "policy-template", is_live_model_output: false, created_at: "" },
  ],
  workflow: { analysis_id: "a1", match_id: "m", snapshot_id: "s", decision_point_id: "dp1", correlation_id: "c", state_version: 3, candidate_action_ids: [], rejected_candidates: [], revision_feedback: [], verification_status: "verified", verification_issues: [], retry_count: 0, explanation_retries: 0, narrative_ids: [], workflow_status: "completed", steps: [
    { step_id: "st1", agent: "decision_agent", task: "Assess", attempt: 1, status: "completed", started_at: "", model: "policy", live_model: false, tool_calls: [{ call_id: "t1", tool_name: "get_decision_context", arguments: {}, result_summary: { ok: true }, status: "ok", duration_ms: 1, started_at: "" }], output: {}, notes: [], handoff_to: "strategy_agent", handoff_reason: "analyse" },
  ], handoffs: [], errors: [], degraded: false, fault_injection: [] },
  model: { agent_mode: "policy", provider: "deterministic-policy", live_model_calls: 0, policy_fallbacks: 0, degraded: false },
  decision_summary: {},
} as unknown as CounterfactualAnalysis;

beforeEach(() => {
  useApp.setState({ decisions: [decision], selectedDecisionId: "dp1", analyses: { dp1: analysis }, mode: "casual", lang: "en", recovery: null, overlays: [] });
});

describe("AnalysisPanel", () => {
  it("casual mode shows simple option cards and the casual narrative", () => {
    render(<AnalysisPanel />);
    expect(screen.getByTestId("casual-cards")).toBeInTheDocument();
    expect(screen.getByText("2.0%")).toBeInTheDocument();
    expect(screen.getByTestId("narrative")).toHaveTextContent("Under our simulation model");
    expect(screen.queryByTestId("analyst-table")).not.toBeInTheDocument();
    expect(screen.getByTestId("verdict")).toHaveTextContent("More promising under the model");
  });

  it("analyst mode adds intervals, comparisons and evidence", () => {
    useApp.setState({ mode: "analyst" });
    render(<AnalysisPanel />);
    expect(screen.getByTestId("analyst-table")).toHaveTextContent("+2.0 pp");
    expect(screen.getByTestId("narrative")).toHaveTextContent("Shoot: P(goal) 0.0%");
    expect(screen.getByTestId("evidence-panel")).toBeInTheDocument();
  });

  it("switches language for labels and number formats", () => {
    useApp.setState({ lang: "nl" });
    render(<AnalysisPanel />);
    expect(screen.getByText("2,0%")).toBeInTheDocument();
    expect(screen.getByTestId("verdict")).toHaveTextContent("Volgens het model kansrijker");
  });

  it("the workflow inspector lists agents and expands tool calls", () => {
    render(<AnalysisPanel />);
    const inspector = screen.getByTestId("workflow-inspector");
    expect(inspector).toHaveTextContent("Decision Agent");
    fireEvent.click(screen.getByText("Decision Agent"));
    expect(inspector).toHaveTextContent("get_decision_context");
  });

  it("draws one branch per option and adds 95% whiskers only for analysts", () => {
    const { unmount } = render(<AnalysisPanel />);
    expect(screen.getAllByTestId(/^option-/)).toHaveLength(2);
    expect(screen.queryAllByTitle("95% interval")).toHaveLength(0);
    unmount();
    useApp.setState({ mode: "analyst" });
    render(<AnalysisPanel />);
    expect(screen.getAllByTitle("95% interval")).toHaveLength(2);
  });

  it("rail tabs switch between story, evidence and agents", () => {
    render(<AnalysisPanel />);
    expect(screen.getByTestId("narrative")).toBeVisible();
    expect(screen.getByTestId("recovery-panel")).not.toBeVisible();
    fireEvent.click(screen.getByTestId("rail-tab-agents"));
    expect(screen.getByTestId("rail-tab-agents")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("recovery-panel")).toBeVisible();
    expect(screen.getByTestId("narrative")).not.toBeVisible();
    fireEvent.click(screen.getByTestId("rail-tab-evidence"));
    expect(screen.getByTestId("evidence-panel")).toBeVisible();
  });

  it("shows a prompt when no decision is selected", () => {
    useApp.setState({ selectedDecisionId: null });
    render(<AnalysisPanel />);
    expect(screen.getByText(/Select a decision/)).toBeInTheDocument();
  });
});

describe("visual components", () => {
  it("ComparisonChart renders one bar per option with an accessible label", () => {
    render(<ComparisonChart candidates={analysis.candidates} results={analysis.simulation!.results} selected={null} lang="en" />);
    expect(screen.getByRole("img", { name: /Comparison chart/ })).toBeInTheDocument();
    expect(screen.getAllByText(/%$/).length).toBeGreaterThan(1);
  });

  it("Pitch renders players and labelled arrows", () => {
    const match = {
      home: { team_id: "HCF", name: "Harbour City FC", short_name: "HCF", color_primary: "#38BDF8", color_secondary: "#000", formation: "" },
      away: { team_id: "NVA", name: "Northvale Athletic", short_name: "NVA", color_primary: "#F59E0B", color_secondary: "#000", formation: "" },
      players: [{ player_id: "H10", team_id: "HCF", shirt_number: 10, role: "AM" }, { player_id: "A06", team_id: "NVA", shirt_number: 6, role: "DM" }],
    } as unknown as MatchInfo;
    let clicked = "";
    render(
      <Pitch match={match} ariaLabel="pitch" onArrowClick={(id) => (clicked = id)}
        frame={{ t_ms: 0, ball: [50, 34, 0], players: { H10: [50, 34], A06: [55, 30] }, possessor_id: "H10" }}
        arrows={[
          { id: "x", from: [50, 34], to: [70, 40], kind: "alternative", label: "Pass to X" },
          { id: "y", from: [60, 25], to: [60, 50], kind: "alternative", label: "Crossing pass" },
        ]} />,
    );
    expect(screen.getByRole("img", { name: "pitch" })).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pass to X" }));
    expect(clicked).toBe("x");
    // SVG uses document paint order: even the last crossing route must be below all labels.
    const routes = screen.getByTestId("pitch-routes");
    const labels = screen.getByTestId("pitch-route-labels");
    expect(routes.compareDocumentPosition(labels) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(labels.querySelectorAll("rect")).toHaveLength(2);
    for (const background of labels.querySelectorAll("rect")) expect(background).toHaveAttribute("fill", "#07160f");
  });
});

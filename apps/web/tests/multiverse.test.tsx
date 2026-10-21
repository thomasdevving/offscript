import type { BranchComparison, BranchNode, MultiverseJob, MultiversePlanning } from "@offscript/contracts";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ActionComposer from "@/components/multiverse/ActionComposer";
import AgentBattle, { PlanningSteps } from "@/components/multiverse/AgentBattle";
import CompareModal from "@/components/multiverse/CompareModal";
import DecisionTree from "@/components/multiverse/DecisionTree";
import type { MvTree, NodeOptions } from "@/lib/multiverseApi";
import { mv, useMv } from "@/lib/mvStore";
import { useApp } from "@/lib/store";
import planningFixture from "./fixtures/mv-planning.json";

// A real planning produced by the backend (pass to Mbeki-Larsen at 72:47), with tool payloads trimmed.
const planning = planningFixture as unknown as MultiversePlanning;
const S = "mv-test";

const tree: MvTree = {
  session_id: S, root_node_id: `${S}~root`, max_depth: 3, mode: "manual",
  nodes: [
    { node_id: `${S}~root`, parent_node_id: null, depth: 0, status: "decision", kind: "root", label: "Decision", outcome: "", children: [`${S}~observed`, `${S}~n002`], match_clock_ms: 4367199, source: null, strategy: null, value_vs_counter: null, verification: null, sample_kind: null },
    { node_id: `${S}~observed`, parent_node_id: `${S}~root`, depth: 1, status: "terminal", kind: "observed", label: "Shoot (actual)", outcome: "SHOT_BLOCKED", children: [], match_clock_ms: 4369749, source: "actual", strategy: null, value_vs_counter: null, verification: null, sample_kind: null },
    { node_id: `${S}~n002`, parent_node_id: `${S}~root`, depth: 1, status: "decision", kind: "simulated", label: "Pass to Mbeki-Larsen", outcome: "completed", children: [], match_clock_ms: 4369088, source: "user", strategy: "Cover lane to Mbeki-Larsen", value_vs_counter: 0.0104, verification: "verified", sample_kind: "representative" },
  ],
};

const node = (over: Partial<BranchNode>): BranchNode => ({
  node_id: `${S}~root`, session_id: S, kind: "root", parent_node_id: null, depth: 0, status: "decision", snapshot_id: "snap",
  match_clock_ms: 4367199, sim_time_ms: 3199, carrier_id: "H10", possession_team_id: "HCF", score: {}, entering_action: null,
  entering_action_source: null, entering_strategy: null, planning_id: null, children: [], label: "Decision", outcome_label: "",
  created_at: "", error: null, fingerprint: null, recommendation_planning_id: null, ...over,
}) as unknown as BranchNode;

const options: NodeOptions = {
  node_id: `${S}~root`, recommendation_planning_id: null,
  actual: { action_id: "a-actual", action_type: "shoot", actor_id: "H10", initial_state_id: "snap", is_actual: true, label: "Shoot (actual)", source: "observed", features: {} } as never,
  options: planning.attack_proposals.slice(0, 2).map((p) => ({ ...p.action, features: { completion_estimate: 0.8 } })) as never,
};

const initial = useMv.getState();

beforeEach(() => {
  useApp.setState({ lang: "en", mode: "analyst" });
  useMv.setState({
    ...initial, tree, selected: `${S}~root`, nodes: { [`${S}~root`]: node({}) }, options: { [`${S}~root`]: options },
    plannings: { [planning.planning_id]: planning }, interaction: "manual",
  });
});

afterEach(() => vi.restoreAllMocks());

describe("DecisionTree", () => {
  it("draws the decision root, the canonical observed branch and simulated branches", () => {
    render(<DecisionTree />);
    expect(screen.getByRole("tree", { name: "Multiverse decision tree" })).toBeInTheDocument();
    expect(screen.getByTestId("tree-node-root")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("tree-node-observed")).toHaveTextContent("ACTUAL");
    const sim = screen.getByTestId("tree-node-simulated");
    expect(sim).toHaveTextContent("USER");
    expect(sim).toHaveTextContent("Pass to Mbeki-Larsen");
    expect(sim).toHaveTextContent("1.0%");
  });

  it("selecting a node rewinds/plays through the store, also from the keyboard", () => {
    const select = vi.spyOn(mv, "select").mockResolvedValue(undefined);
    render(<DecisionTree />);
    fireEvent.click(screen.getByTestId("tree-node-simulated"));
    expect(select).toHaveBeenCalledWith(`${S}~n002`, { play: true });
    fireEvent.keyDown(screen.getByTestId("tree-node-root"), { key: "Enter" });
    expect(select).toHaveBeenCalledWith(`${S}~root`, { play: false });
  });

  it("shows a pending ghost branch while agents plan", () => {
    const job = { job_id: "j", parent_node_id: `${S}~root`, status: "running", progress: ["defending agent: round 2"] } as unknown as MultiverseJob;
    useMv.setState({ job });
    render(<DecisionTree />);
    expect(screen.getByText("Agents planning…")).toBeInTheDocument();
    expect(screen.getByText("defending agent: round 2")).toBeInTheDocument();
  });
});

describe("AgentBattle and response matrix", () => {
  it("shows each round's attacking and defending proposals", () => {
    render(<AgentBattle p={planning} />);
    const battle = screen.getByTestId("agent-battle");
    expect(within(battle).getByText("Round 1")).toBeInTheDocument();
    expect(within(battle).getByText(`Round ${planning.rounds.length}`)).toBeInTheDocument();
    expect(battle).toHaveTextContent("+ Pass to Mbeki-Larsen");
    expect(battle).toHaveTextContent("+ Cover lane to Mbeki-Larsen");
    expect(battle).toHaveTextContent("deterministic planner");
  });

  it("renders the matrix with one cell per evaluated pair and marks the defensive counter", () => {
    render(<AgentBattle p={planning} />);
    const matrix = screen.getByTestId("response-matrix");
    const strategies = new Set(planning.matrix.map((c) => c.strategy_id));
    expect(within(matrix).getAllByRole("columnheader")).toHaveLength(strategies.size + 1);
    expect(within(matrix).getByText(/Cover lane to Mbeki-Larsen ★/)).toBeInTheDocument();
    const cell = planning.matrix.find((c) => c.strategy_id === planning.summary!.defensive_counter_id && c.action_id === planning.summary!.selected_action_id)!;
    expect(within(matrix).getAllByText(`${(cell.xg * 100).toFixed(1)}%`).length).toBeGreaterThan(0);
    expect(matrix).toHaveTextContent(`${planning.rollouts_per_cell} paired simulations`);
  });

  it("summarises robust/upside/expected choices and the verification result", () => {
    render(<AgentBattle p={planning} />);
    const summary = screen.getByTestId("strategy-summary");
    expect(summary).toHaveTextContent("Most robustPass to Mbeki-Larsen");
    const upside = planning.attack_proposals.find((a) => a.action.action_id === planning.summary!.highest_upside_action_id)!;
    expect(summary).toHaveTextContent(`Highest upside${upside.action.label}`);
    expect(summary).toHaveTextContent("-0.3 pp");
    const n = planning.verification_checks.length;
    expect(screen.getByTestId("mv-verification")).toHaveTextContent(`✓ verified (${n}/${n} checks)`);
  });

  it("does not present a failed verification as verified", () => {
    const failed = { ...planning, verification_status: "failed", verification_checks: planning.verification_checks.map((c, i) => (i === 0 ? { ...c, passed: false } : c)) };
    render(<AgentBattle p={failed as MultiversePlanning} />);
    expect(screen.getByTestId("mv-verification")).not.toHaveTextContent("✓");
    render(<PlanningSteps p={failed as MultiversePlanning} />);
    expect(screen.getByTestId("mv-steps")).toHaveTextContent("✗");
  });

  it("the steps inspector lists both adversarial agents and their tools", () => {
    render(<PlanningSteps p={planning} />);
    const steps = screen.getByTestId("mv-steps");
    expect(steps).toHaveTextContent("attacking");
    expect(steps).toHaveTextContent("defending");
    expect(steps).toHaveTextContent("evaluate_response_matrix");
  });
});

describe("ActionComposer", () => {
  it("manual mode offers tools and options, and only submits a validated action", () => {
    const choose = vi.spyOn(mv, "chooseCandidate").mockResolvedValue(undefined);
    render(<ActionComposer />);
    expect(screen.getByTestId("tool-pass")).toBeInTheDocument();
    expect(screen.getByText("ACTUAL")).toBeInTheDocument();
    expect(screen.getByTestId("submit-action")).toBeDisabled();
    fireEvent.click(screen.getAllByTestId("option")[0]);
    expect(choose).toHaveBeenCalledWith(planning.attack_proposals[0].action.action_id);
    expect(screen.queryByTestId("recommend")).not.toBeInTheDocument();
    expect(screen.queryByTestId("autoplay")).not.toBeInTheDocument();
  });

  it("shows validation results, enabling submit only when feasible", () => {
    const submit = vi.spyOn(mv, "submit").mockResolvedValue(undefined);
    useMv.setState({ composer: { type: null, targetId: null, point: null, candidateId: null, validation: { ok: false, code: "TARGET_UNREACHABLE", message: "No teammate can reach that point" } as never } });
    const { rerender } = render(<ActionComposer />);
    expect(screen.getByTestId("validation")).toHaveTextContent("TARGET_UNREACHABLE");
    expect(screen.getByTestId("submit-action")).toBeDisabled();
    useMv.setState({ composer: { type: null, targetId: null, point: null, candidateId: null, validation: { ok: true, action: { label: "Pass to Mbeki-Larsen" } } as never } });
    rerender(<ActionComposer />);
    expect(screen.getByTestId("validation")).toHaveTextContent("Pass to Mbeki-Larsen is feasible");
    fireEvent.click(screen.getByTestId("submit-action"));
    expect(submit).toHaveBeenCalled();
  });

  it("assisted mode asks the attacking agent and labels its recommendation", () => {
    const recommend = vi.spyOn(mv, "recommend").mockResolvedValue(undefined);
    const accept = vi.spyOn(mv, "acceptRecommendation").mockResolvedValue(undefined);
    useMv.setState({ interaction: "assisted" });
    const { rerender } = render(<ActionComposer />);
    fireEvent.click(screen.getByTestId("recommend"));
    expect(recommend).toHaveBeenCalled();
    useMv.setState({ nodes: { [`${S}~root`]: node({ recommendation_planning_id: planning.planning_id }) } });
    rerender(<ActionComposer />);
    expect(screen.getByText(/AI recommends/)).toHaveTextContent("Pass to Mbeki-Larsen");
    expect(screen.getByText("AI RECOMMENDED")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("accept-recommendation"));
    expect(accept).toHaveBeenCalled();
  });

  it("autonomous mode hands both sides to the agents", () => {
    const auto = vi.spyOn(mv, "autoPlay").mockResolvedValue(undefined);
    useMv.setState({ interaction: "autonomous" });
    render(<ActionComposer />);
    expect(screen.queryByTestId("tool-pass")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("autoplay"));
    expect(auto).toHaveBeenCalledWith(3);
  });

  it("the canonical observed branch cannot be changed", () => {
    useMv.setState({ selected: `${S}~observed`, nodes: { [`${S}~observed`]: node({ node_id: `${S}~observed`, kind: "observed", status: "terminal", parent_node_id: `${S}~root` }) } });
    render(<ActionComposer />);
    expect(screen.getByTestId("no-decision")).toHaveTextContent("cannot be changed");
    expect(screen.queryByTestId("submit-action")).not.toBeInTheDocument();
  });

  it("switching interaction mode goes through the store", () => {
    const set = vi.spyOn(mv, "setInteraction");
    render(<ActionComposer />);
    fireEvent.click(screen.getByTestId("mode-assisted"));
    expect(set).toHaveBeenCalledWith("assisted");
  });
});

describe("CompareModal", () => {
  it("shows both branches side by side with metrics and the grounded explanation", () => {
    const data = {
      node_a: `${S}~observed`, node_b: `${S}~n002`,
      metrics_a: { kind: "observed", final_outcome: "SHOT_BLOCKED", elapsed_s: 2.6, shots: 1, turnovers: 0 },
      metrics_b: { kind: "simulated", final_outcome: "completed", elapsed_s: 1.9, shots: 0, turnovers: 0 },
      steps_a: [{ node_id: `${S}~observed`, action_label: "Shoot (actual)", action_source: "actual", strategy_label: null, first_outcome: "SHOT_BLOCKED", terminal_outcome: null, p_goal_vs_counter: null }],
      steps_b: [{ node_id: `${S}~n002`, action_label: "Pass to Mbeki-Larsen", action_source: "user", strategy_label: "Cover lane to Mbeki-Larsen", first_outcome: "completed", terminal_outcome: null, p_goal_vs_counter: 0.0104 }],
      explanation: "Both branches start from the same frozen state at 72:47.",
    } as unknown as BranchComparison;
    useMv.setState({ compare: { ...initial.compare, open: true, data } });
    render(<CompareModal />);
    const modal = screen.getByTestId("compare-modal");
    expect(modal).toHaveTextContent("A · Canonical synthetic timeline");
    expect(modal).toHaveTextContent("B · Simulated branch");
    expect(modal).toHaveTextContent("(user vs Cover lane to Mbeki-Larsen)");
    expect(modal).toHaveTextContent("SHOT BLOCKED");
    expect(screen.getByTestId("compare-explanation")).toHaveTextContent("same frozen state");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(useMv.getState().compare.open).toBe(false);
  });

  it("renders nothing when closed", () => {
    const { container } = render(<CompareModal />);
    expect(container).toBeEmptyDOMElement();
  });
});

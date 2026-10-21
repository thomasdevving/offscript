import { expect, test } from "@playwright/test";

/**
 * Mirrors the final acceptance workflow: load "Shoot or Pass", play, detect the decision,
 * verified multi-agent analysis, viewer modes, what-if playback, workflow inspector,
 * controlled recovery, broadcast overlay JSON, Dutch, recap, scenario switching.
 */
test("shoot-or-pass end to end", async ({ page }) => {
  await page.goto("/app/?scenario=shoot_vs_pass");
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /73' - The decision that changed the attack/ })).toBeVisible();
  await expect(page.getByTestId("agent-mode")).toContainText("Agents");

  // Play at 4x until OFFSCRIPT detects the decision and auto-pauses.
  await page.getByRole("button", { name: "4×" }).click();
  await page.getByTestId("play-toggle").click();
  await expect(page.getByTestId("event-feed")).toContainText("Shot");
  await expect(page.getByTestId("view-banner")).toContainText("Frozen decision state");

  // Multi-agent analysis completes and is verified.
  const panel = page.getByTestId("analysis-panel");
  await expect(panel).toContainText("Ravi Castellane");
  await expect(page.getByTestId("verified-badge")).toBeVisible();
  await expect(page.getByTestId("verdict")).toBeVisible();
  await expect(page.getByTestId("option-actual")).toContainText("Shoot");
  expect(await page.getByTestId("option-alt").count()).toBeGreaterThanOrEqual(1);
  await expect(page.getByTestId("narrative")).toContainText("Under our simulation model");

  // Tactical analyst mode: table, intervals, evidence, verification checks.
  await page.getByRole("radio", { name: "Tactical analyst" }).click();
  await expect(page.getByTestId("analyst-table")).toContainText("pp");
  await expect(page.getByTestId("evidence-panel")).toContainText("Every candidate action is feasible from the snapshot");
  await expect(page.getByTestId("evidence-panel")).toContainText("Rollouts per option");

  // What-if playback of an alternative.
  await page.getByTestId("analyst-table").getByRole("button").nth(1).click();
  await expect(page.getByTestId("view-banner")).toContainText("Simulated alternative");
  await expect(page.getByTestId("whatif-controls")).toBeVisible();
  await expect(page.getByTestId("trace-label")).toContainText("rollout #");
  await page.getByTestId("back-to-match").click();
  await expect(page.getByTestId("view-banner")).toContainText("Observed synthetic timeline");

  // Agent workflow inspector shows the real steps and tool calls (Agents tab of the decision rail).
  await page.getByTestId("rail-tab-agents").click();
  const steps = page.getByTestId("workflow-steps");
  await expect(steps).toContainText("Decision Agent");
  await expect(steps).toContainText("Strategy Agent");
  await expect(steps).toContainText("Simulation Agent");
  await expect(steps).toContainText("Verification Agent");
  await expect(steps).toContainText("Explanation Agent");

  // Controlled recovery: an invalid alternative is rejected and the workflow recovers.
  await page.getByTestId("fault-invalid_candidate").click();
  await expect(page.getByTestId("workflow-inspector")).toContainText("Rejected proposals");
  await expect(page.getByTestId("workflow-inspector")).toContainText("PLAYER_NOT_ON_PITCH");
  await expect(page.getByTestId("workflow-status")).toContainText("completed · verified");
  await page.getByRole("button", { name: /main analysis/ }).click();

  // Broadcaster mode: machine-readable overlay instructions.
  await page.getByRole("radio", { name: "Broadcaster" }).click();
  await expect(page.getByTestId("overlay-json")).toContainText("decision_comparison");
  await expect(page.getByTestId("caption")).toContainText("Model");

  // Dutch.
  await page.getByRole("radio", { name: "NL" }).click();
  await expect(page.getByTestId("caption")).toContainText("Model");
  await expect(page.getByTestId("verdict")).toContainText("model");

  // Recap.
  await page.getByTestId("open-recap").click();
  await expect(page.getByTestId("recap")).toContainText("Harbour City FC");
  await page.getByRole("button", { name: "Sluiten" }).click();

  // Switch scenario.
  await page.getByTestId("scenario-select").selectOption("risky_through_ball");
  await expect(page.getByRole("heading", { name: /risky through ball/ })).toBeVisible();
});

test("keyboard and decision timeline navigation", async ({ page }) => {
  await page.goto("/app/?scenario=shoot_vs_pass");
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  await expect(page.getByTestId("decision-list")).toContainText("Ravi Castellane");
  await page.keyboard.press("ArrowRight");
  await expect(page.getByTestId("view-banner")).toContainText("Frozen decision state");
  await expect(page.getByTestId("analysis-panel")).toContainText("Ravi Castellane");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("view-banner")).toContainText("Observed synthetic timeline");
});

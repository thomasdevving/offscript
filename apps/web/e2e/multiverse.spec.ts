import { expect, test } from "@playwright/test";

const API = process.env.E2E_API_URL ?? "http://localhost:8000";

/**
 * Football Multiverse end to end against the real backend: decision -> user pass -> adversarial
 * planning -> branch -> second decision -> rewind -> sibling branch -> compare -> inspector, and the
 * canonical match timeline is unchanged.
 */
test("football multiverse: branch, continue, rewind, fork, compare", async ({ page, request }) => {
  test.setTimeout(300_000);
  const before = await (await request.get(`${API}/api/matches/demo-match-073/events`)).json();
  const decisions = await (await request.get(`${API}/api/matches/demo-match-073/decisions`)).json();

  await page.goto("/?scenario=shoot_vs_pass&view=multiverse");
  await page.getByTestId("mv-open-decision").first().click();
  await expect(page.getByTestId("decision-tree")).toBeVisible();
  await expect(page.getByTestId("tree-node-observed")).toBeVisible();
  await expect(page.getByTestId("mv-banner")).toContainText("Frozen decision state");

  // 1) User picks the alternative pass on the pitch.
  await page.getByTestId("tool-pass").click();
  await page.getByTestId("player-H07").dispatchEvent("click");
  await expect(page.getByTestId("validation")).toContainText("feasible");
  await page.getByTestId("submit-action").click();
  await expect(page.getByTestId("tree-node-simulated")).toHaveCount(1, { timeout: 120_000 });
  await expect(page.getByTestId("mv-banner")).toContainText("Simulated branch");
  await expect(page.getByTestId("mv-narrative")).toContainText("defending agent");

  // 2) Agents and verification are observable.
  await page.getByRole("radio", { name: "Tactical analyst" }).click();
  await expect(page.getByTestId("response-matrix")).toBeVisible();
  await expect(page.getByTestId("agent-battle")).toContainText("Attacking agent");
  await expect(page.getByTestId("agent-battle")).toContainText("Defending agent");
  await expect(page.getByTestId("mv-verification")).toContainText("verified");
  await page.getByTestId("mv-inspector").locator("summary").click();
  await expect(page.getByTestId("mv-steps")).toContainText("attacking");
  await expect(page.getByTestId("mv-steps")).toContainText("defending");

  // 3) Second decision from the simulated state (if the representative continuation kept the ball).
  const composer = page.getByTestId("action-composer");
  if (await composer.isVisible()) {
    await page.getByTestId("tool-shoot").click();
    await expect(page.getByTestId("validation")).toContainText("feasible");
    await page.getByTestId("submit-action").click();
    await expect(page.getByTestId("tree-node-simulated")).toHaveCount(2, { timeout: 120_000 });
  }
  const simulatedBeforeFork = await page.getByTestId("tree-node-simulated").count();

  // 4) Rewind to the original decision: the exact frozen state is restored.
  await page.getByTestId("tree-node-root").click();
  await expect(page.getByTestId("mv-banner")).toContainText("Frozen decision state");
  const rootId = await page.getByTestId("tree-node-root").getAttribute("data-node-id");
  const state = await (await request.get(`${API}/api/multiverse/branches/${encodeURIComponent(rootId!)}/state`)).json();
  expect(state.snapshot_id).toBe(decisions[0].snapshot_id);

  // 5) A sibling branch: dribble instead.
  await page.getByRole("radio", { name: "Casual fan" }).click();
  await page.getByTestId("option").filter({ hasText: "Dribble" }).first().click();
  await expect(page.getByTestId("validation")).toContainText("feasible");
  await page.getByTestId("submit-action").click();
  await expect(page.getByTestId("tree-node-simulated")).toHaveCount(simulatedBeforeFork + 1, { timeout: 120_000 });

  // 6) Compare two branches side by side.
  await page.getByTestId("compare-with").first().click();
  await expect(page.getByTestId("compare-modal")).toBeVisible();
  await expect(page.getByTestId("compare-explanation")).toContainText("same frozen state");
  await page.getByRole("button", { name: "Close" }).last().click();

  // 7) The canonical synthetic match is unchanged and the live view still works.
  const after = await (await request.get(`${API}/api/matches/demo-match-073/events`)).json();
  expect(after.length).toBe(before.length);
  expect(after[after.length - 1].event_id).toBe(before[before.length - 1].event_id);
  await page.getByTestId("tab-live").click();
  await expect(page.getByTestId("view-banner")).toBeVisible();
});

import { expect, test } from "@playwright/test";

/** Captures README screenshots from the real running app. Run with: SCREENSHOTS=1 npx playwright test screenshots */
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");

const OUT = "../../docs/images";

test("capture product screenshots", async ({ page }) => {
  await page.goto("/?scenario=shoot_vs_pass");
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "2×" }).click();
  await page.getByTestId("play-toggle").click();
  await expect(page.getByTestId("verified-badge")).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/casual-decision.png` });

  await page.getByRole("radio", { name: "Tactical analyst" }).click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/analyst-mode.png`, fullPage: true });

  await page.getByRole("radio", { name: "Casual fan" }).click();
  await page.getByTestId("option-alt").first().click();
  await expect(page.getByTestId("view-banner")).toContainText("Simulated alternative");
  await page.waitForTimeout(1800);
  await page.screenshot({ path: `${OUT}/what-if-playback.png` });

  await page.getByTestId("back-to-match").click();
  await page.getByRole("radio", { name: "Broadcaster" }).click();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowRight");
  await expect(page.getByTestId("overlay-json")).toBeVisible();
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/broadcaster-mode.png` });

  await page.getByRole("radio", { name: "Tactical analyst" }).click();
  await page.getByTestId("fault-contradictory_claim").click();
  await expect(page.getByTestId("workflow-status")).toContainText("completed · verified");
  const inspector = page.getByTestId("workflow-inspector");
  await inspector.scrollIntoViewIfNeeded();
  await inspector.screenshot({ path: `${OUT}/agent-recovery.png` });
});

test("capture multiverse screenshots", async ({ page }) => {
  test.setTimeout(300_000);
  await page.goto("/?scenario=shoot_vs_pass&view=multiverse");
  await page.getByTestId("mv-open-decision").first().click();
  await expect(page.getByTestId("tree-node-observed")).toBeVisible();
  await page.getByTestId("tool-pass").click();
  await page.getByTestId("player-H07").dispatchEvent("click");
  await expect(page.getByTestId("validation")).toContainText("feasible");
  await page.getByTestId("submit-action").click();
  await expect(page.getByTestId("tree-node-simulated")).toHaveCount(1, { timeout: 120_000 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${OUT}/multiverse-branch.png` });

  await page.getByRole("radio", { name: "Tactical analyst" }).click();
  const battle = page.getByTestId("agent-battle");
  await battle.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await battle.screenshot({ path: `${OUT}/multiverse-agent-battle.png` });

  await page.getByRole("radio", { name: "Casual fan" }).click();
  await page.getByTestId("tree-node-root").click();
  await page.getByTestId("option").filter({ hasText: "Dribble" }).first().click();
  await expect(page.getByTestId("validation")).toContainText("feasible");
  await page.getByTestId("submit-action").click();
  await expect(page.getByTestId("tree-node-simulated")).toHaveCount(2, { timeout: 120_000 });
  await page.getByTestId("compare-with").first().click();
  await expect(page.getByTestId("compare-explanation")).toBeVisible();
  await page.getByRole("button", { name: "Play both" }).click();
  await page.waitForTimeout(1500);
  await page.getByTestId("compare-modal").locator("> div").screenshot({ path: `${OUT}/multiverse-compare.png` });
});

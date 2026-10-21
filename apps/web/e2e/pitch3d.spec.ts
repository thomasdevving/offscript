import { expect, test } from "@playwright/test";

/** The 3D replay renders the same timeline as the 2D board and keeps the decision flow playable. */
test("3D replay: frozen decision, simulated continuation and outcome", async ({ page }) => {
  await page.goto("/app/?scenario=shoot_vs_pass");
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  await page.getByTestId("dim-3d").click();
  await expect(page.getByTestId("pitch-3d").locator("canvas")).toBeVisible();
  await page.getByRole("button", { name: "2×" }).click();
  await page.getByTestId("play-toggle").click();
  await expect(page.getByTestId("verified-badge")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("view-banner")).toContainText("Frozen decision state");

  await page.getByTestId("option-alt").first().click();
  await expect(page.getByTestId("view-banner")).toContainText("Simulated alternative");
  await expect(page.getByTestId("outcome-card")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("outcome-card")).toContainText("one simulated continuation");
  await expect(page.getByTestId("outcome-card")).toContainText("P(goal)");

  // The choice is remembered and 2D stays one click away.
  await page.reload();
  await expect(page.getByTestId("dim-3d")).toHaveAttribute("aria-checked", "true");
  await page.getByTestId("dim-2d").click();
  await expect(page.getByTestId("pitch-3d")).toHaveCount(0);
});

test("3D replay in the Multiverse: pick a teammate on the 3D pitch and watch the branch", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/app/?scenario=shoot_vs_pass&view=multiverse&dim=3d");
  await page.getByTestId("mv-open-decision").first().click();
  await expect(page.getByTestId("tree-node-observed")).toBeVisible();
  const canvas = page.getByTestId("pitch-3d").locator("canvas");
  await expect(canvas).toBeVisible();
  await page.getByTestId("tool-pass").click();
  // The broadcast camera eases after the ball; wait until it is still before aiming.
  const screenOf = () => page.evaluate(() => (window as unknown as { __pitch3d?: { screenOf(id: string): [number, number] | null } })
    .__pitch3d?.screenOf("H07") ?? null);
  let [x, y] = [0, 0];
  await expect.poll(async () => {
    const a = await screenOf();
    await page.waitForTimeout(250);
    const b = await screenOf();
    if (!a || !b) return Infinity;
    [x, y] = b;
    return Math.hypot(a[0] - b[0], a[1] - b[1]);
  }, { timeout: 20_000 }).toBeLessThan(1);
  await canvas.click({ position: { x, y } });
  await expect(page.getByTestId("validation")).toContainText("feasible");
  await page.getByTestId("submit-action").click();
  await expect(page.getByTestId("tree-node-simulated")).toHaveCount(1, { timeout: 120_000 });
  await expect(page.getByTestId("outcome-card")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("outcome-card")).toContainText("one simulated continuation");
});

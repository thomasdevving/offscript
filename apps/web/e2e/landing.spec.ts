import { expect, test } from "@playwright/test";

/** The landing page's agent relay shows what each agent did on the 73' decision, and stations are clickable. */
test("agent relay walks through the five agents of the 73' run", async ({ page }) => {
  await page.goto("/");
  const relay = page.getByTestId("agent-relay");
  await relay.scrollIntoViewIfNeeded();
  await page.getByTestId("relay-2").click();
  await expect(relay).toContainText("Simulation Agent · 7.2 s");
  await expect(relay).toContainText("200 rollouts/option ready");
  await page.getByTestId("relay-3").click();
  await expect(relay).toContainText("Claims match the evidence table");
  await expect(page.getByTestId("relay-3")).toHaveAttribute("aria-pressed", "true");
});

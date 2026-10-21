import { expect, test } from "@playwright/test";

const theme = (page: import("@playwright/test").Page) => page.evaluate(() => document.documentElement.dataset.theme);

/** Light is the default; the header toggle switches to dark and the choice survives a reload. */
test("light theme by default, dark on request and remembered", async ({ page }) => {
  await page.goto("/");
  expect(await theme(page)).toBe("light");
  await page.goto("/app/?scenario=shoot_vs_pass");
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  expect(await theme(page)).toBe("light");
  await page.getByTestId("theme-toggle").click();
  expect(await theme(page)).toBe("dark");
  await page.reload();
  expect(await theme(page)).toBe("dark");
  await page.goto("/?theme=light");
  expect(await theme(page)).toBe("light");
});

import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const localVenv = path.resolve(process.cwd(), "..", "api", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const PY = process.env.PARALLEL_PYTHON ?? `"${localVenv}"`;

/**
 * End-to-end tests drive the real stack: FastAPI backend (deterministic policy agents, so no
 * cloud credentials are needed) + the Next.js frontend, in a real Chromium.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    viewport: { width: 1600, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 1000 } } }],
  webServer: [
    {
      command: `${PY} -m uvicorn app.main:app --app-dir ../api --port 8000`,
      url: "http://localhost:8000/api/health",
      reuseExistingServer: true,
      timeout: 120_000,
      env: { AGENT_MODE: "policy", USE_ANALYSIS_CACHE: "false" },
    },
    {
      command: "npx next dev -p 3000",
      url: "http://localhost:3000",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});

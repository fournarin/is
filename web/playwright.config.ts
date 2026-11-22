import { defineConfig } from "@playwright/test";

/**
 * End-to-end flows and the accessibility scan (ADR-144), against a running
 * stack: a built web server and the API over a seeded demo world. Nothing here
 * starts one, because the world is shared state - the flows change it, so they
 * run one at a time, in file order, on a world reset before the run.
 *
 *   E2E_WEB_URL=http://localhost:3001 DATABASE_URL=postgresql://.../pdm_web_check_v2 npx playwright test
 *
 * The browser is the installed Chrome (`channel: "chrome"`), so no browser
 * download is needed on a plant machine without internet.
 */
export default defineConfig({
  testDir: "e2e",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 120_000,
  reporter: [["list"], ["json", { outputFile: "test-results/e2e.json" }]],
  use: {
    baseURL: process.env.E2E_WEB_URL ?? "http://localhost:3001",
    channel: "chrome",
    locale: "th-TH",
    timezoneId: "Asia/Bangkok",
    trace: "retain-on-failure",
  },
});

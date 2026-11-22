import { defineConfig } from "@playwright/test";

/**
 * The before/after measurement of the screens (docs/results/before-after.md),
 * kept apart from the e2e flows because it is run once per version, each on a
 * freshly reset world, and is a count rather than a pass/fail:
 *
 *   UI_VERSION=v2 MEASURE_WEB_URL=http://localhost:3001 DATABASE_URL=... npx playwright test -c playwright.measure.config.ts
 *   UI_VERSION=v1 MEASURE_WEB_URL=http://127.0.0.1:3005 REPORT_MACHINE=<from v2> DATABASE_URL=... npx playwright test -c playwright.measure.config.ts
 */
export default defineConfig({
  testDir: "measure",
  workers: 1,
  retries: 0,
  timeout: 120_000,
  reporter: [["list"]],
  use: {
    baseURL: process.env.MEASURE_WEB_URL ?? "http://localhost:3001",
    channel: "chrome",
    locale: "th-TH",
    timezoneId: "Asia/Bangkok",
  },
});

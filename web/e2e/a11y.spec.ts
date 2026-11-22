import { mkdirSync, writeFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

import { type Scan, as, axe, workingJob } from "./world";

/**
 * An axe-core scan of every screen of the second frontend (ADR-144), first in
 * the run so it sees the world before the flows change it. Serious and
 * critical violations fail the test; the rest are recorded in
 * test-results/axe.json for docs/results/e2e.md. axe tests what a machine can:
 * keyboard order, zoom, greyscale and screen-reader sense are not claimed.
 */

const PHONE = { width: 390, height: 844 };
const DESK = { width: 1280, height: 800 };
const found: Record<string, Scan> = {};

async function scan(name: string, page: import("@playwright/test").Page): Promise<void> {
  await page.waitForLoadState("networkidle");
  const scanned = await axe(page);
  found[name] = scanned;
  expect(scanned.passed, `${name}: axe ran no rules`).toBeGreaterThan(0);
  const bad = scanned.violations.filter((one) => one.impact === "serious" || one.impact === "critical");
  expect.soft(bad, `${name}: ${bad.map((one) => `${one.id} (${one.nodes})`).join(", ")}`).toEqual([]);
}

test.afterAll(() => {
  mkdirSync("test-results", { recursive: true });
  writeFileSync("test-results/axe.json", JSON.stringify(found, null, 1));
});

test("sign-in", async ({ browser }) => {
  const page = await (await browser.newContext({ viewport: PHONE })).newPage();
  await page.goto("/sign-in");
  await scan("sign-in@390", page);
});

test("operator report", async ({ browser }) => {
  const { context, page } = await as(browser, "op-1", PHONE);
  await page.goto("/report");
  await scan("report-stations@390", page);
  await page.goto("/report?machine=MC-012");
  await scan("report-form@390", page);
  await context.close();
});

test("shift lead board", async ({ browser }) => {
  const { context, page } = await as(browser, "sup-1", DESK);
  await page.goto("/board");
  await scan("board@1280", page);
  await page.locator(".focal details.sheet.dw > summary").click();
  await scan("board-drawer@1280", page);
  await context.close();
  const phone = await as(browser, "sup-1", PHONE);
  await phone.page.goto("/board");
  await scan("board@390", phone.page);
  await phone.context.close();
});

test("technician screens", async ({ browser }) => {
  const { ref, user } = workingJob();
  const { context, page } = await as(browser, user, PHONE);
  await page.goto("/work");
  await scan("tech-job@390", page);
  await page.goto(`/work/${ref}/steps`);
  await scan("tech-step@390", page);
  await page.goto(`/work/${ref}/steps?step=1`);
  const manual = await page.locator("a.mref").first().getAttribute("href");
  if (manual) {
    await page.goto(manual);
    await scan("tech-manual@390", page);
  }
  await page.goto(`/work/${ref}/close?reached=1`);
  await scan("tech-close@390", page);
  await page.goto(`/work/${ref}/handover?reached=1`);
  await scan("tech-handover@390", page);
  await context.close();
});

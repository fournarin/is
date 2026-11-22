import { execFileSync } from "node:child_process";
import { join } from "node:path";

import type { Browser, BrowserContext, Page } from "@playwright/test";

/**
 * The seeded demo world the flows run on, and the two ways a test reaches past
 * the screen: signing in through the real form, and reading the database to
 * say what a tap actually changed. A test that only reads the screen it just
 * drew would pass on a screen that lies.
 */

// The passwords `scripts/seed_demo.py --demo-passwords` sets. Demo accounts
// only; a plant machine is seeded without that flag and has none of them.
export const PASSWORDS: Record<string, string> = {
  "op-1": "demo-operator",
  "sup-1": "demo-supervisor",
  "tech-1": "demo-technician",
  "tech-2": "demo-technician-2",
  "tech-3": "demo-technician-3",
};

const PSQL = process.env.PSQL ?? "psql";

function database(): string {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("set DATABASE_URL to the database the stack under test uses");
  return url;
}

/** One query, rows as arrays of strings. */
export function rows(query: string): string[][] {
  const out = execFileSync(PSQL, [database(), "-AtF", "\t", "-c", query], { encoding: "utf8" });
  return out
    .split("\n")
    .filter((line) => line !== "")
    .map((line) => line.split("\t"));
}

export function one(query: string): string {
  const found = rows(query);
  if (found.length === 0) throw new Error(`no row for: ${query}`);
  return found[0]![0]!;
}

export function run(statement: string): void {
  execFileSync(PSQL, [database(), "-qc", statement]);
}

/**
 * The job the seed leaves under way, with a step that isolates energy. Which
 * machine it is depends on the round that placed it, so it is looked up, not
 * named.
 */
export function workingJob(): { ref: string; user: string } {
  const [ref, user] = one(
    `SELECT work_order_ref || ':' || (assignees->0->>'user') FROM work_order
      WHERE status = 'in_progress' AND jsonb_path_exists(playbook_snapshot, '$[*].isolation_points[*]')
      ORDER BY machine_id = 'MC-012' DESC, work_order_ref LIMIT 1`,
  ).split(":");
  return { ref: ref!, user: user! };
}

export async function signIn(page: Page, user: string): Promise<void> {
  await page.goto("/sign-in");
  await page.fill("input[name=user]", user);
  await page.fill("input[name=password]", PASSWORDS[user]!);
  // Pressed after hydration, so the action posts as the app does.
  await page.waitForLoadState("networkidle");
  await page.locator("form button[type=submit]").click();
  await page.waitForURL((url) => !url.pathname.startsWith("/sign-in"));
}

export async function as(browser: Browser, user: string, viewport = { width: 390, height: 844 }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  await signIn(page, user);
  return { context, page };
}

// Playwright loads the specs as CommonJS, so the path is from here, not import.meta.
export const AXE_SOURCE = join(__dirname, "..", "node_modules", "axe-core", "axe.min.js");

export type Violation = { id: string; impact: string | null; help: string; nodes: number; targets: string[] };
export type Scan = { violations: Violation[]; passed: number; incomplete: { id: string; nodes: number }[] };

/**
 * WCAG 2.2 A and AA as axe-core tests them; what it cannot test is not claimed.
 * The rules that passed and those axe could not decide ("incomplete", for a
 * person to look at) are kept, so an empty list of violations is visibly a scan
 * that ran.
 */
export async function axe(page: Page): Promise<Scan> {
  await page.addScriptTag({ path: AXE_SOURCE });
  return page.evaluate(async () => {
    type Rule = { id: string; impact: string | null; help: string; nodes: { target: string[] }[] };
    const result = await (window as unknown as { axe: { run: (context: Document, options: object) => Promise<{ violations: Rule[]; passes: Rule[]; incomplete: Rule[] }> } }).axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    });
    return {
      violations: result.violations.map((one) => ({
        id: one.id,
        impact: one.impact,
        help: one.help,
        nodes: one.nodes.length,
        targets: one.nodes.slice(0, 5).map((node) => node.target.join(" ")),
      })),
      passed: result.passes.length,
      incomplete: result.incomplete.map((one) => ({ id: one.id, nodes: one.nodes.length })),
    };
  });
}

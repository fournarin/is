import { mkdirSync, writeFileSync } from "node:fs";

import { type Locator, type Page, expect, test } from "@playwright/test";

import { as, one, workingJob } from "../e2e/world";

/**
 * The same three tasks on the first frontend (v1, f1499b8) and the second (v2),
 * on the same seeded world through the same API. What the trial technician said
 * was wrong with v1 was too much text and too many places to look, so that is
 * what is counted: (a) actions to finish - taps, a pick from a list, a field
 * typed in, a file chosen - (b) words of visible text on each screen passed
 * through, counted with the browser's Thai word segmenter, and (c) screens
 * visited. A measurement of the screens, not a usability result: nobody used
 * them while this ran.
 */

type Action = { kind: "tap" | "pick" | "type" | "file"; what: string; characters?: number };
type Screen = { path: string; words: number };
type Task = { task: string; done: boolean; actions: Action[]; screens: Screen[]; note?: string };

const VERSION = process.env.UI_VERSION ?? "v2";
const PHONE = { width: 390, height: 844 };
const results: Task[] = [];

const WORDS = () => {
  const text = document.body.innerText;
  const segmenter = new Intl.Segmenter("th", { granularity: "word" });
  let count = 0;
  for (const piece of segmenter.segment(text)) if (piece.isWordLike) count += 1;
  return count;
};

class Meter {
  readonly actions: Action[] = [];
  readonly screens: Screen[] = [];
  constructor(private readonly page: Page) {}

  async look(): Promise<void> {
    // "/" only redirects to the role's own home; the home is the first screen.
    await this.page.waitForURL((url) => url.pathname !== "/");
    await this.page.waitForLoadState("networkidle");
    const url = new URL(this.page.url());
    const path = url.pathname + url.search;
    if (this.screens.at(-1)?.path !== path) this.screens.push({ path, words: await this.page.evaluate(WORDS) });
  }

  /** `goes`: the tap is a link or a posted form, so the screen is read after the address changes. */
  async tap(target: Locator, what: string, goes = false): Promise<void> {
    const before = this.page.url();
    await target.click();
    this.actions.push({ kind: "tap", what });
    if (goes) await this.page.waitForURL((url) => url.href !== before);
    await this.look();
  }

  async pick(target: Locator, value: string, what: string): Promise<void> {
    await target.selectOption(value);
    this.actions.push({ kind: "pick", what });
    await this.look();
  }

  async type(target: Locator, text: string, what: string): Promise<void> {
    await target.fill(text);
    this.actions.push({ kind: "type", what, characters: [...text].length });
    await this.look();
  }

  async file(target: Locator, buffer: Buffer, what: string): Promise<void> {
    await target.setInputFiles({ name: "leak.jpg", mimeType: "image/jpeg", buffer });
    this.actions.push({ kind: "file", what });
    await this.look();
  }
}

async function photo(page: Page): Promise<Buffer> {
  const data = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 3200;
    canvas.height = 2400;
    const pen = canvas.getContext("2d")!;
    pen.fillStyle = "#7a8490";
    pen.fillRect(0, 0, 3200, 2400);
    return canvas.toDataURL("image/jpeg", 0.9).split(",")[1]!;
  });
  return Buffer.from(data, "base64");
}

test.afterAll(() => {
  mkdirSync("test-results", { recursive: true });
  writeFileSync(`test-results/before-after-${VERSION}.json`, JSON.stringify({ version: VERSION, tasks: results }, null, 1));
});

test("the technician opens the job and the manual page for step 1", async ({ browser }) => {
  const { user } = workingJob();
  const { context, page } = await as(browser, user, PHONE);
  const meter = new Meter(page);
  await meter.look();
  if (VERSION === "v1") {
    await meter.tap(page.locator('a.button-link.big[href$="/steps"]'), "ทำต่อ →", true);
    await meter.tap(page.locator("a.button-link.quiet", { hasText: "อ่านคู่มือหน้า" }).first(), "อ่านคู่มือหน้า", true);
  } else {
    await meter.tap(page.locator('main a[href$="/steps"]').first(), "the job's steps", true);
    await meter.tap(page.locator("a.mref").first(), "คู่มือหน้า", true);
  }
  const done = new URL(page.url()).pathname.endsWith("/manual");
  results.push({ task: "technician: job, then the manual page of step 1", done, actions: meter.actions, screens: meter.screens });
  await context.close();
});

test("the operator reports a machine with a photo", async ({ browser }) => {
  const { context, page } = await as(browser, "op-1", PHONE);
  const meter = new Meter(page);
  await meter.look();
  let note: string | undefined;
  let machine: string | null;
  if (VERSION === "v1") {
    machine = process.env.REPORT_MACHINE ?? null;
    expect(machine, "REPORT_MACHINE: the machine the v2 run reported").not.toBeNull();
    await meter.pick(page.locator("select[name=machine_id]"), machine!, "เครื่องไหน");
    await meter.type(page.locator("textarea[name=description]"), "รั่ว / ซึม", "เห็นอะไร");
    note = "v1 has no photo: the report was sent without one";
    await meter.tap(page.locator("form:has(select[name=machine_id]) button[type=submit]"), "แจ้งงานเสีย");
    const again = page.locator("form:has(select[name=machine_id]) button[type=submit]", { hasText: "นี่คนละเรื่อง" });
    const sent = page.locator("a", { hasText: "แจ้งเรื่องอื่น" });
    await expect(again.or(sent).first()).toBeVisible();
    if (await again.isVisible()) await meter.tap(again, "ยืนยัน: นี่คนละเรื่อง");
  } else {
    await meter.tap(page.locator("a.rp-go").first(), "station", true);
    if (new URL(page.url()).searchParams.has("station")) await meter.tap(page.locator("a.rp-go").first(), "machine", true);
    machine = new URL(page.url()).searchParams.get("machine");
    await meter.tap(page.locator("label.ch:has(input[name=stopped][value=no])"), "หยุดไหม: ไม่");
    await meter.tap(page.locator('label.ch:has(input[name=seen][value="รั่ว / ซึม"])'), "รั่ว / ซึม");
    await meter.file(page.locator("input[name=photo]"), await photo(page), "รูปถ่าย");
    await meter.tap(page.locator(".submit button[type=submit]"), "ส่ง");
    const again = page.getByRole("button", { name: "ส่ง: นี่คนละเรื่อง" });
    await expect(again.or(page.locator(".rp-sent"))).toBeVisible();
    if (await again.isVisible()) await meter.tap(again, "ส่ง: นี่คนละเรื่อง");
  }
  await expect(page.locator(VERSION === "v1" ? "a:has-text('แจ้งเรื่องอื่น')" : ".rp-sent")).toBeVisible();
  const made = one(`SELECT count(*) FROM work_order WHERE origin = 'manual' AND machine_id = '${machine}' AND created_at > now() - interval '2 minutes'`);
  results.push({ task: `operator: report ${machine} with a photo`, done: made !== "0", actions: meter.actions, screens: meter.screens, note });
  await context.close();
});

test("the shift lead confirms the top job", async ({ browser }) => {
  const { context, page } = await as(browser, "sup-1", { width: 1280, height: 800 });
  const meter = new Meter(page);
  await meter.look();
  const form = VERSION === "v1" ? page.locator("form:has(button.ok)").first() : page.locator(".focal .acts > form");
  const ref = await form.locator("input[name=ref]").inputValue();
  await meter.tap(form.locator("button[type=submit]"), VERSION === "v1" ? "✓ ยืนยัน" : "ยืนยันให้ …", true);
  const done = one(`SELECT status FROM work_order WHERE work_order_ref = '${ref}'`) === "assigned";
  results.push({ task: `shift lead: confirm the top job (${ref})`, done, actions: meter.actions, screens: meter.screens });
  await context.close();
});

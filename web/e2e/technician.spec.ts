import { type Locator, expect, test } from "@playwright/test";

import { as, one, run, workingJob } from "./world";

/**
 * The technician's job from the job page to closed (sets 1-2, ADR-134 to
 * ADR-138), by tapping what the screen offers and nothing else: every point
 * switched off and locked, the wait, the zero-energy check, the restore checks
 * and the locks off, then the close sent while the phone is offline and
 * delivered when it comes back. The waits are real minutes, so the test moves
 * the recorded start back instead of sleeping.
 */

/**
 * A tap on a server-action form redraws the step, and the button it pressed
 * goes with it; a click still being retried then has nothing to press. Gone
 * after the tap is the tap having worked, which the next pass of the loop reads.
 */
async function tap(target: Locator): Promise<void> {
  const before = await target.innerText().catch(() => "");
  try {
    await target.click({ timeout: 10_000 });
  } catch (error) {
    if ((await target.count()) > 0) throw error;
  }
  // Wait for the redraw, so the loop reads the step after the tap, not before it.
  await expect
    .poll(async () => ((await target.count()) === 0 ? null : await target.innerText().catch(() => null)), { timeout: 10_000 })
    .not.toBe(before)
    .catch(() => undefined);
}

test("a technician works the isolation job through to closed, closing offline", async ({ browser }) => {
  const { ref, user } = workingJob();
  test.setTimeout(300_000);
  const { context, page } = await as(browser, user, { width: 390, height: 844 });

  await page.goto("/work");
  await expect(page.locator("body")).toContainText(ref);
  await page.goto(`/work/${ref}/steps`);

  const tapped: string[] = [];
  for (let guard = 0; guard < 120; guard += 1) {
    await page.waitForLoadState("networkidle");
    const close = page.getByRole("link", { name: "ครบทุกขั้น ปิดงาน" });
    if ((await close.count()) > 0) {
      await close.click();
      break;
    }
    const lock = page.locator("form.lockpick");
    const point = page.locator("form button.ch.box");
    const wait = page.getByRole("button", { name: /เริ่มนับเวลารอ/ });
    const next = page.locator(".done-btn form button.btn.pri");
    if ((await lock.count()) > 0) {
      if ((await lock.locator("input[type=radio]").count()) === 0) await lock.locator("input[name=lock_other]").fill("ก-77");
      tapped.push("ใส่กุญแจ");
      await tap(lock.locator("button[type=submit]"));
    } else if ((await point.count()) > 0) {
      tapped.push((await point.first().innerText()).replace(/\s+/g, " ").trim());
      await tap(point.first());
    } else if ((await wait.count()) > 0) {
      tapped.push("เริ่มนับเวลารอ");
      await tap(wait);
    } else if ((await next.count()) > 0) {
      await tap(next);
    } else if ((await page.locator("[role=timer]").count()) > 0) {
      run(`UPDATE step_confirmation SET confirmed_at = confirmed_at - interval '60 minutes' WHERE work_order_ref = '${ref}' AND item = 'wait_started'`);
      await page.reload();
    } else {
      const shown = (await page.locator("main").innerText()).replace(/\s+/g, " ").slice(0, 600);
      throw new Error(`nothing to tap on ${page.url()} after ${tapped.join(" / ")}: ${shown}`);
    }
  }

  // Each kind of energy step was met and confirmed on the way.
  expect(tapped.some((one) => one.startsWith("ปิด"))).toBe(true);
  expect(tapped).toContain("ใส่กุญแจ");
  expect(tapped.some((one) => one.includes("พลังงานเป็นศูนย์"))).toBe(true);
  expect(tapped.some((one) => one.startsWith("ปลดกุญแจ"))).toBe(true);
  expect(one(`SELECT count(*) FROM lock_record WHERE work_order_ref = '${ref}' AND released_at IS NULL`)).toBe("0");

  await page.waitForURL(/\/close/);
  await page.locator("label.ch:has(input[name=outcome][value=fixed])").click();
  await page.locator("label.ch:has(input[name=lock_state][value=released])").click();
  await page.locator(".submit button[type=submit]").click();
  await expect(page.locator("#sum-h")).toBeVisible();

  await context.setOffline(true);
  await expect(page.locator(".offline-tag")).toBeVisible();
  await page.getByRole("button", { name: "ยืนยันปิดงาน" }).click();
  await expect(page.locator("body")).toContainText("ยังส่งไม่ได้ เก็บไว้ในเครื่องแล้ว");
  expect(one(`SELECT status FROM work_order WHERE work_order_ref = '${ref}'`)).toBe("in_progress");

  await context.setOffline(false);
  await page.getByRole("button", { name: "ลองส่งเดี๋ยวนี้" }).click();
  await expect(page.locator("body")).toContainText("ส่งการปิดงานแล้ว");
  expect(one(`SELECT status FROM work_order WHERE work_order_ref = '${ref}'`)).toBe("closed");
  await context.close();
});

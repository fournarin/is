import { expect, test } from "@playwright/test";

import { as, one } from "./world";

/**
 * The shift lead's board (set 3, ADR-141): confirm the job the board puts
 * first, then set the next one aside with a reason. Each tap is checked in the
 * database as well as on the screen: the board redrawing is not the same thing
 * as the order being assigned.
 */

test("the lead confirms the top job, and sets the next aside with a reason", async ({ browser }) => {
  const { context, page } = await as(browser, "sup-1", { width: 1280, height: 800 });
  await page.goto("/board");

  const confirm = page.locator(".focal .acts > form");
  const top = await confirm.locator("input[name=ref]").inputValue();
  await expect(confirm.locator("button")).toContainText("ยืนยันให้");
  await confirm.locator("button").click();
  await page.waitForURL(/\/board/);
  await page.waitForLoadState("networkidle");
  expect(one(`SELECT status FROM work_order WHERE work_order_ref = '${top}'`)).toBe("assigned");
  await expect(page.locator(".focal .acts > form input[name=ref]")).not.toHaveValue(top);

  const next = await page.locator(".focal .acts > form input[name=ref]").inputValue();
  const reason = `e2e: รอหยุดสายตอนพักเที่ยง ${Date.now()}`;
  await page.locator(".focal details.sheet.menu > summary").click();
  const aside = page.locator(".focal details.sheet.menu form.aside");
  await aside.locator("textarea[name=reason]").fill(reason);
  await aside.locator("button[type=submit]").click();
  await page.waitForURL(/\/board/);
  await page.waitForLoadState("networkidle");

  expect(one(`SELECT state || '|' || reason FROM dispatch_proposal WHERE work_order_ref = '${next}' AND reason IS NOT NULL ORDER BY decided_at DESC LIMIT 1`)).toBe(`rejected|${reason}`);
  // Back in the queue, not dropped: the next round may offer it again.
  expect(one(`SELECT status FROM work_order WHERE work_order_ref = '${next}'`)).toBe("queued");
  // Set aside is shown, with its reason, in the board's own tab.
  await expect(page.locator("body")).toContainText(reason);
  await context.close();
});

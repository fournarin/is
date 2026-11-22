import { expect, test } from "@playwright/test";

import { as, one } from "./world";

/**
 * The operator's report (set 4, ADR-142), the way someone on the floor makes
 * one: the station list, the machine, three answers by tap, one photo, send.
 * The photo is drawn here rather than kept as a file, larger than the 1600 px
 * the phone shrinks it to, so the shrinking is exercised too.
 */

test("an operator reports a machine with a photo", async ({ browser }) => {
  const { context, page } = await as(browser, "op-1", { width: 390, height: 844 });
  await page.goto("/report");
  await page.locator("a.rp-go").first().click();
  await page.waitForLoadState("networkidle");
  if (new URL(page.url()).searchParams.has("station")) {
    await page.locator("a.rp-go").first().click();
    await page.waitForLoadState("networkidle");
  }
  const machine = new URL(page.url()).searchParams.get("machine");
  expect(machine).not.toBeNull();

  await page.locator("label.ch:has(input[name=stopped][value=no])").click();
  await page.locator('label.ch:has(input[name=seen][value="รั่ว / ซึม"])').click();

  const jpeg = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 3200;
    canvas.height = 2400;
    const pen = canvas.getContext("2d")!;
    const fill = pen.createLinearGradient(0, 0, 3200, 2400);
    fill.addColorStop(0, "#5a6470");
    fill.addColorStop(1, "#c9ced4");
    pen.fillStyle = fill;
    pen.fillRect(0, 0, 3200, 2400);
    return canvas.toDataURL("image/jpeg", 0.9).split(",")[1]!;
  });
  await page.setInputFiles("input[name=photo]", { name: "leak.jpg", mimeType: "image/jpeg", buffer: Buffer.from(jpeg, "base64") });
  await expect(page.locator(".rp-photo img")).toBeVisible();

  await page.locator(".submit button[type=submit]").click();
  // A machine that already has an open report asks first (ADR-142 §4); the
  // photo has to survive that answer, which is the bug the window-2 checks caught.
  const again = page.getByRole("button", { name: "ส่ง: นี่คนละเรื่อง" });
  await expect(again.or(page.locator(".rp-sent"))).toBeVisible();
  if (await again.isVisible()) {
    await expect(page.locator(".rp-photo img")).toBeVisible();
    await again.click();
  }
  const sent = page.locator(".rp-sent");
  await expect(sent).toContainText("ส่งแล้ว");
  const ref = (await sent.locator(".code").first().textContent())!.trim();

  expect(one(`SELECT machine_id FROM work_order WHERE work_order_ref = '${ref}'`)).toBe(machine);
  expect(one(`SELECT origin FROM work_order WHERE work_order_ref = '${ref}'`)).toBe("manual");
  expect(one(`SELECT count(*) FROM work_order_photo WHERE work_order_ref = '${ref}'`)).toBe("1");
  // Shrunk on the phone before it was sent: well under the 2 MB the API takes.
  expect(Number(one(`SELECT size_bytes FROM work_order_photo WHERE work_order_ref = '${ref}'`))).toBeLessThan(1_000_000);
  await context.close();
});

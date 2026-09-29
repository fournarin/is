/**
 * The pages a step sends the technician to, read out of its words.
 *
 * 2026-09-29: "Isolate the cabinet following the lockout procedure on page 2"
 * was cited to page 5, and page 5 was the only page the screen opened. The
 * lockout is the step a technician must not skip.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { pagesNamed } from "./page-references.ts";

test("an English step naming a page", () => {
  assert.deepEqual(
    pagesNamed("Isolate the cabinet following the lockout procedure on page 2.", 5),
    [2],
  );
});

test("the approver's Thai naming a page", () => {
  assert.deepEqual(pagesNamed("ตัดพลังงานตู้ควบคุมตามขั้นตอนล็อกเอาต์ในหน้า 2", 5), [2]);
});

test("a range is every page in it, and both languages together are read once", () => {
  assert.deepEqual(
    pagesNamed("See pages 12-14 for the wiring. ดูหน้า 12 ด้วย", 5),
    [12, 13, 14],
  );
});

test("the page the step is cited to is not offered twice", () => {
  assert.deepEqual(pagesNamed("as shown on page 5", 5), []);
});

test("figures that are not pages are not pages", () => {
  assert.deepEqual(
    pagesNamed("Torque to 42 Nm, wait 3 minutes, fan reaches 1500 rpm within 30 seconds.", 4),
    [],
  );
});

test("a range too long to be a reference is not turned into a hundred links", () => {
  assert.deepEqual(pagesNamed("pages 1-400", 9), [1, 400]);
});

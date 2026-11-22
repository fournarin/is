import assert from "node:assert/strict";
import { test } from "node:test";

import { bannerFor } from "./banners.ts";

const TITLE = "MC-001 มอเตอร์สายพานร้อนเกินกำหนด";

test("a confirmation names the machine, the symptom and who it went to", () => {
  // Fourth trial, finding 8: "ยืนยัน WO-000011 แล้ว" named nothing checkable.
  const said = bannerFor("confirmed", "WO-000011", TITLE, ["สมชาย"]);
  assert.match(said, /ยืนยันงาน MC-001 มอเตอร์สายพานร้อนเกินกำหนด แล้ว ส่งถึง สมชาย แล้ว/);
  assert.doesNotMatch(said, /WO-000011/);
});

test("setting aside, bringing back and releasing name the job too", () => {
  assert.match(bannerFor("rejected", "WO-000012", TITLE), /พักงาน MC-001 มอเตอร์สายพานร้อนเกินกำหนด ไว้แล้ว/);
  assert.match(bannerFor("brought", "WO-000012", TITLE), /นำงาน MC-001 .* กลับมาแล้ว/);
  assert.match(bannerFor("released", "WO-000012", TITLE), /ปล่อยงาน MC-001 .* แล้ว/);
});

test("a ticket that could not be read falls back to its number", () => {
  assert.match(bannerFor("confirmed", "WO-000011", null), /^ยืนยัน WO-000011 แล้ว งานถูกส่งถึงช่างแล้ว$/);
});

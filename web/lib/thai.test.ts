import assert from "node:assert/strict";
import { test } from "node:test";

import { thaiPieces } from "./thai.ts";

test("the pieces put back together are the sentence, unchanged", () => {
  const sentence = "ปิดเบรกเกอร์ CP-3 ที่ตู้ควบคุม แล้วใส่กุญแจล็อกและป้ายของตัวเอง ตามขั้นตอนล็อกเอาต์หน้า 2";
  assert.equal(thaiPieces(sentence).join(""), sentence);
});

test("a compound the dictionary splits stays one piece", () => {
  const pieces = thaiPieces("ใส่กุญแจและป้ายของตัวเอง");
  assert.ok(pieces.includes("ของตัวเอง"), pieces.join("|"));
  assert.ok(thaiPieces("รอหัวหน้ากะยืนยัน").includes("หัวหน้ากะ"));
});

test("codes and a number with its unit never break inside", () => {
  const pieces = thaiPieces("โหลดหน้า 143 ของ R-2000iC ไม่ได้ · เลยมา 2 วัน · MC-012");
  for (const whole of ["R-2000iC", "2 วัน", "MC-012"]) {
    assert.ok(pieces.includes(whole), `${whole} in ${pieces.join("|")}`);
  }
});

test("text with no Thai and no code is one piece", () => {
  assert.deepEqual(thaiPieces("Remove the belt guard."), ["Remove the belt guard."]);
});

test("ๆ never starts a piece", () => {
  for (const piece of thaiPieces("ใบงานอื่น ๆ ที่เปิดอยู่")) {
    assert.ok(!piece.startsWith("ๆ"), piece);
  }
});

import assert from "node:assert/strict";
import { test } from "node:test";

import { pageParagraphs } from "./page-text.ts";

const PAGE_4 =
  "Belt motor overheating - corrective procedure\nSymptom: belt motor temperature above 85 degrees Celsius. " +
  "1. Isolate the cell following the lockout procedure on page 2. 2. Remove the belt guard. 3. Measure " +
  "deflection under 20 N of\napplied force. 6. Refit the guard. Confirm the housing temperature settles\nbelow " +
  "70 degrees Celsius. Required tools: torque wrench 5-60 Nm, 10 mm socket. Estimated time: 45 minutes.\n\n" +
  "Required skill: robot mechanical.\n";

test("the first short line without a full stop is the heading", () => {
  assert.equal(pageParagraphs(PAGE_4).heading, "Belt motor overheating - corrective procedure");
});

test("numbered items and label sentences start their own lines; wrap points do not", () => {
  assert.deepEqual(pageParagraphs(PAGE_4).paragraphs, [
    "Symptom: belt motor temperature above 85 degrees Celsius.",
    "1. Isolate the cell following the lockout procedure on page 2.",
    "2. Remove the belt guard.",
    "3. Measure deflection under 20 N of applied force.",
    "6. Refit the guard. Confirm the housing temperature settles below 70 degrees Celsius.",
    "Required tools: torque wrench 5-60 Nm, 10 mm socket.",
    "Estimated time: 45 minutes.",
    "Required skill: robot mechanical.",
  ]);
});

test("nothing is reworded: the words in equal the words out", () => {
  const { heading, paragraphs } = pageParagraphs(PAGE_4);
  const words = (text: string) => text.split(/\s+/).filter(Boolean);
  assert.deepEqual(words([heading, ...paragraphs].join(" ")), words(PAGE_4));
});

test("a page that opens with a sentence has no heading", () => {
  assert.equal(pageParagraphs("Replace the belt at 8000 hours.\nThe idler is 18 Nm.").heading, null);
});

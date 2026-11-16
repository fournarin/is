import assert from "node:assert/strict";
import { test } from "node:test";

import { stillNeeded, waitEnds } from "./energy.ts";
import type { PointConfirmed, Step } from "./work.ts";

const BASE: Step = { text: "x", text_th: null, source_doc: "d", page: 2, manual: null };
const CP3 = { point_id: "CP-3", label: "breaker", energy: "electrical" };
const at = (minutes: number) => new Date(Date.UTC(2026, 2, 3, 8, minutes));
const done = (item: string, point_id = "CP-3", step = 2, minutes = 0): PointConfirmed => ({
  step,
  point_id,
  item,
  by: "tech-1",
  at: at(minutes).toISOString(),
});

test("isolation is off then locked, and only this step's confirmations count", () => {
  const isolate: Step = { ...BASE, kind: "isolation", isolation_points: [CP3] };
  assert.deepEqual(stillNeeded(isolate, 2, [], at(0)), [
    { point_id: "CP-3", item: "off" },
    { point_id: "CP-3", item: "locked" },
  ]);
  assert.deepEqual(stillNeeded(isolate, 2, [done("off"), done("locked", "CP-3", 5)], at(0)), [
    { point_id: "CP-3", item: "locked" },
  ]);
});

test("a wait counts from when it started", () => {
  const hot: Step = { ...BASE, kind: "hazard", wait_minutes: 30 };
  const started = [done("wait_started", "", 3, 0)];
  assert.equal(waitEnds(hot, 3, started)?.toISOString(), at(30).toISOString());
  assert.equal(stillNeeded(hot, 3, started, at(29)).length, 1);
  assert.equal(stillNeeded(hot, 3, started, at(30)).length, 0);
});

test("an unmarked step needs nothing", () => {
  assert.deepEqual(stillNeeded(BASE, 1, [], at(0)), []);
});

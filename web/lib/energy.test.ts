import assert from "node:assert/strict";
import { test } from "node:test";

import { firstUnfinished, nextLine, stillNeeded, waitEnds } from "./energy.ts";
import type { LockOn, PointConfirmed, Step } from "./work.ts";

const BASE: Step = { text: "x", text_th: null, source_doc: "d", page: 2, manual: null };
const CP3 = { point_id: "CP-3", label: "breaker", energy: "electrical" };
const ISOLATE: Step = { ...BASE, kind: "isolation", isolation_points: [CP3] };
const at = (minutes: number) => new Date(Date.UTC(2026, 2, 3, 8, minutes));
const done = (item: string, point_id = "CP-3", step = 2, by = "tech-1", minutes = 0): PointConfirmed => ({
  step,
  point_id,
  item,
  by,
  at: at(minutes).toISOString(),
});
const lock = (owner = "tech-1"): LockOn => ({
  point_id: "CP-3",
  lock_no: "ก-03",
  owner,
  owner_name: owner,
  work_order_ref: "WO-1",
  step: 2,
  applied_at: at(0).toISOString(),
});
const me = (locksOn: LockOn[] = [], user = "tech-1") => ({ user, locksOn, checks: ["tools_removed"] });

test("isolation is off then your own lock, on now", () => {
  assert.deepEqual(stillNeeded(ISOLATE, 2, [], at(0), me()), [
    { point_id: "CP-3", item: "off" },
    { point_id: "CP-3", item: "locked" },
  ]);
  const said = [done("off"), done("locked")];
  assert.deepEqual(stillNeeded(ISOLATE, 2, said, at(0), me([])), [{ point_id: "CP-3", item: "locked" }]);
  assert.deepEqual(stillNeeded(ISOLATE, 2, said, at(0), me([lock()])), []);
  assert.deepEqual(stillNeeded(ISOLATE, 2, said, at(0), me([lock()], "tech-2")), [{ point_id: "CP-3", item: "locked" }]);
});

test("restore asks for the plant's checks, then every lock off", () => {
  const restore: Step = { ...BASE, kind: "restore", isolation_points: [CP3] };
  assert.deepEqual(stillNeeded(restore, 7, [], at(0), me([lock("tech-2")])), [
    { point_id: "tools_removed", item: "checked" },
    { point_id: "CP-3", item: "released" },
  ]);
  // Past the restore step, the isolation no longer asks for the lock that came off there.
  const steps = [ISOLATE, restore, BASE];
  const said = [done("off", "CP-3", 1), done("checked", "tools_removed", 2)];
  assert.equal(firstUnfinished(steps, said, 3, at(0), me([])), null);
});

test("taking the lock off in the restore step does not reopen the isolation behind it", () => {
  const restore: Step = { ...BASE, kind: "restore", isolation_points: [CP3] };
  const steps = [BASE, ISOLATE, restore, BASE];
  const said = [done("off"), done("locked"), done("checked", "tools_removed", 3)];
  // On the restore step with the lock already off: step 2 is not unfinished.
  assert.equal(firstUnfinished(steps, said, 3, at(0), me([])), null);
  // On a normal step after the isolation with the lock gone, it still is.
  assert.deepEqual(firstUnfinished([BASE, ISOLATE, BASE], said, 3, at(0), me([])), {
    number: 2,
    missing: [{ point_id: "CP-3", item: "locked" }],
  });
});

test("a wait counts from when it started", () => {
  const hot: Step = { ...BASE, kind: "hazard", wait_minutes: 30 };
  const started = [done("wait_started", "", 3)];
  assert.equal(waitEnds(hot, 3, started)?.toISOString(), at(30).toISOString());
  assert.equal(stillNeeded(hot, 3, started, at(29), me()).length, 1);
  assert.equal(stillNeeded(hot, 3, started, at(30), me()).length, 0);
});

test("an unmarked step needs nothing", () => {
  assert.deepEqual(stillNeeded(BASE, 1, [], at(0), me()), []);
});

test("the sticky link names what is next and where, not the step's own name", () => {
  const verify = [
    { point_id: "TP-1", item: "verified" },
    { point_id: "TP-2", item: "verified" },
  ];
  assert.equal(nextLine(verify), "ต่อไป: วัดที่ TP-1 / TP-2");
  assert.equal(nextLine([{ point_id: "CP-3", item: "locked" }]), "ต่อไป: ใส่กุญแจของคุณ ที่ CP-3");
  assert.equal(nextLine([{ point_id: "CP-3", item: "wait_started" }]), "ต่อไป: รอให้ครบเวลา");
});

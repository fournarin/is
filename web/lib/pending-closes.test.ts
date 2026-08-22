/**
 * The offline queue, without a browser.
 *
 * `node --test` runs TypeScript directly on Node 24, so this needs no test
 * framework and no new dependency - which matters, because CLAUDE.md wants an
 * ADR for one and a queue of four functions is not the argument for it.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { STORAGE_KEY, type PendingClose, type StorageLike, enqueue, pending, settle } from "./pending-closes.ts";

function storage(initial: string | null = null): StorageLike & { raw: () => string | null } {
  let held = initial;
  return {
    getItem: () => held,
    setItem: (_key: string, value: string) => {
      held = value;
    },
    raw: () => held,
  };
}

function close(ref: string, overrides: Partial<PendingClose> = {}): PendingClose {
  return {
    ref,
    outcome: "fixed",
    blocked_reason: [],
    blocked_minutes: 0,
    technician_feedback: null,
    queued_at: "2026-03-03T08:00:00Z",
    ...overrides,
  };
}

test("nothing queued reads as nothing", () => {
  assert.deepEqual(pending(storage()), []);
});

test("a queued close survives being read back", () => {
  const device = storage();
  enqueue(device, close("WO-000001", { outcome: "no_problem_found" }));

  // A fresh read from the same storage is what a reload does.
  const [only] = pending(device);
  assert.equal(only?.ref, "WO-000001");
  assert.equal(only?.outcome, "no_problem_found");
});

test("closing the same job twice queues it once, keeping the later answer", () => {
  const device = storage();
  enqueue(device, close("WO-000001", { outcome: "temporary_fix" }));
  enqueue(device, close("WO-000001", { outcome: "fixed" }));

  const queue = pending(device);
  assert.equal(queue.length, 1, "two closes of one job are the same close");
  assert.equal(queue[0]?.outcome, "fixed");
});

test("two jobs queue separately", () => {
  const device = storage();
  enqueue(device, close("WO-000001"));
  enqueue(device, close("WO-000002"));

  assert.deepEqual(
    pending(device).map((one) => one.ref),
    ["WO-000001", "WO-000002"],
  );
});

test("settling one leaves the other", () => {
  const device = storage();
  enqueue(device, close("WO-000001"));
  enqueue(device, close("WO-000002"));

  settle(device, "WO-000001");

  assert.deepEqual(
    pending(device).map((one) => one.ref),
    ["WO-000002"],
  );
});

test("settling something that was never queued is not an error", () => {
  const device = storage();
  assert.deepEqual(settle(device, "WO-999999"), []);
});

test("unreadable storage reads as empty rather than throwing", () => {
  // A phone that white-screens has lost the queue and the screen.
  assert.deepEqual(pending(storage("{not json")), []);
  assert.deepEqual(pending(storage("null")), []);
  assert.deepEqual(pending(storage('"a string"')), []);
});

test("entries that are not closes are dropped rather than trusted", () => {
  const device = storage(JSON.stringify([{ ref: "WO-1" }, close("WO-000002")]));

  assert.deepEqual(
    pending(device).map((one) => one.ref),
    ["WO-000002"],
  );
});

test("the key is stable, because a rename orphans every queued close", () => {
  assert.equal(STORAGE_KEY, "pdm.pending-closes");
});

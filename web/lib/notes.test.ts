import assert from "node:assert/strict";
import { test } from "node:test";

import { bySymptom, type FloorNote } from "./notes.ts";

const note = (ref: string, symptom: string | null): FloorNote => ({
  work_order_ref: ref,
  machine_id: "MC-001",
  symptom_code: symptom,
  playbook_ref: null,
  outcome: "fixed",
  closed_at: "2026-09-29T08:00:00Z",
  note: "หมายเหตุ",
});

test("notes are grouped by symptom, groups in the order of their newest note", () => {
  const groups = bySymptom([note("WO-3", "SYM-021"), note("WO-2", "SYM-014"), note("WO-1", "SYM-021")]);

  assert.deepEqual(
    groups.map(([symptom, notes]) => [symptom, notes.map((one) => one.work_order_ref)]),
    [
      ["SYM-021", ["WO-3", "WO-1"]],
      ["SYM-014", ["WO-2"]],
    ],
  );
});

test("a note with no symptom is still shown, under its own heading", () => {
  const [[heading]] = bySymptom([note("WO-9", null)]);

  assert.equal(heading, "ไม่ระบุอาการ");
});

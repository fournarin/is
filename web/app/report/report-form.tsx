"use client";

import Link from "next/link";
import { useActionState } from "react";

import { type ReportState, reportFault } from "@/app/report/actions";
import type { Machine } from "@/lib/report";

// Here rather than in `actions.ts`: a `"use server"` file may only export async
// functions, and a constant beside the action is the mistake that shape invites.
const NOTHING_REPORTED: ReportState = {
  error: null,
  openOrders: [],
  created: null,
  values: { machineId: "", severity: "medium", description: "" },
};

// ADR-077 §2. `critical` is not offered, and the screen says why rather than
// leaving somebody looking for the strongest word and not finding it.
const LEVELS = [
  { value: "low", label: "ไม่ด่วน", hint: "ทำงานได้อยู่ รอรอบซ่อมได้" },
  { value: "medium", label: "ควรดู", hint: "ผิดปกติ แต่ยังเดินเครื่องได้" },
  { value: "high", label: "ด่วน", hint: "กระทบการผลิต หรือกำลังจะกระทบ" },
];

/**
 * The one screen in this system where a person tells it something it did not
 * already know.
 *
 * Three fields and nothing else: which machine, how bad, what you saw. Anything
 * more is a form somebody abandons standing at a machine, and a fault reported
 * by radio instead is the state this slice exists to leave behind.
 */
export function ReportForm({ machines }: { machines: Machine[] }) {
  const [state, action, pending] = useActionState(reportFault, NOTHING_REPORTED);

  // `key` on the form is what makes the echoed values above take effect without
  // JavaScript: React reuses the DOM it already rendered otherwise, and the
  // fresh page from a refusal would come back with the fields it started with.
  const attempt = `${state.error ?? ""}${state.openOrders.join(",")}`;

  if (state.created !== null) {
    return (
      <div className="card">
        <p>
          รับเรื่องแล้ว <strong>{state.created}</strong>
        </p>
        <p className="muted">
          ระบบจะเลือกช่างภายในไม่กี่นาที แล้วหัวหน้ากะยืนยันก่อนส่งถึงช่าง ดูความคืบหน้าได้ที่ “เรื่องที่คุณแจ้งไว้” ด้านล่าง
        </p>
        <p>
          <Link href="/">กลับหน้าแรก</Link>
        </p>
      </div>
    );
  }

  return (
    <form action={action} key={attempt}>
      {state.error !== null && (
        <p className="error" role="alert">
          {state.error}
        </p>
      )}

      {/* Carried back into the next submission, so "this is something else" is
          an answer about the tickets the person was actually shown. */}
      {state.openOrders.map((ref) => (
        <input key={ref} type="hidden" name="distinct_from" value={ref} />
      ))}

      <label className="field">
        <span>เครื่องไหน</span>
        <select name="machine_id" required defaultValue={state.values.machineId}>
          <option value="" disabled>
            เลือกเครื่อง
          </option>
          {machines.map((machine) => (
            <option key={machine.machine_id} value={machine.machine_id}>
              {machine.machine_id} · {machine.station_id} ({machine.model})
            </option>
          ))}
        </select>
      </label>

      <fieldset className="field">
        <legend>ด่วนแค่ไหน</legend>
        {LEVELS.map((level, index) => (
          <label key={level.value} className="choice">
            <input
              type="radio"
              name="severity"
              value={level.value}
              defaultChecked={
                state.values.severity === "" ? index === 1 : state.values.severity === level.value
              }
              required
            />
            <span>
              {level.label}
              <span className="muted"> — {level.hint}</span>
            </span>
          </label>
        ))}
        <p className="muted">
          ถ้ารอรอบถัดไปไม่ได้ ให้โทรหาหัวหน้ากะ แล้วแจ้งในระบบทีหลัง ระบบนี้เป็นคิวงาน ไม่ใช่ช่องทางฉุกเฉิน
        </p>
      </fieldset>

      <label className="field">
        <span>เห็นอะไร</span>
        <textarea
          name="description"
          rows={4}
          required
          defaultValue={state.values.description}
          placeholder="เช่น มีน้ำมันไหลใต้ฐาน ประมาณฝ่ามือ ตั้งแต่ต้นกะ"
        />
      </label>

      <button type="submit" disabled={pending}>
        {pending
          ? "กำลังส่ง..."
          : state.openOrders.length > 0
            ? "ยืนยัน: นี่คนละเรื่องกับงานที่ค้างอยู่"
            : "แจ้งงานเสีย"}
      </button>
    </form>
  );
}

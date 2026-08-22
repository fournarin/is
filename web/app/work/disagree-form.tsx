"use client";

import { useActionState } from "react";

import { type ObjectionState, disagree } from "@/app/work/actions";
import { plantTime } from "@/lib/display";

// Here and not in `actions.ts`: a `"use server"` file may only export async
// functions, and a constant beside the action that returns it is the mistake
// that shape invites. `next build` catches this one; it did not catch the
// same thing on the sign-in form in slice 10.1.
const NOT_OBJECTED: ObjectionState = { error: null, recordedAt: null };

/**
 * Sits beside the reason, where somebody is already reading it.
 *
 * Not in a menu: ADR-005 says a system that cannot explain itself gets
 * overruled and then abandoned, and the objection belongs at the moment of
 * disbelief rather than three taps away from it.
 */
export function DisagreeForm({ workOrder, timezone }: { workOrder: string; timezone: string }) {
  const [state, action, pending] = useActionState(disagree, NOT_OBJECTED);

  if (state.recordedAt !== null) {
    return (
      <p className="recorded">
        บันทึกไว้แล้วเมื่อ {plantTime(state.recordedAt, timezone)} — ลำดับงานไม่เปลี่ยน
        ซึ่งตั้งใจให้เป็นอย่างนั้น สิ่งที่มีค่าคือบันทึกนี้
      </p>
    );
  }

  return (
    <details>
      <summary>ไม่เห็นด้วยกับลำดับนี้</summary>
      <form action={action}>
        <input type="hidden" name="ref" value={workOrder} />
        {state.error !== null && (
          <p className="error" role="alert">
            {state.error}
          </p>
        )}
        <label className="field">
          <span>ทำไมถึงไม่ควรเป็นงานนี้ก่อน</span>
          <textarea name="reason" rows={3} required placeholder="เช่น MC-004 หยุดสายจริง งานนี้รอได้" />
        </label>
        <button type="submit" className="quiet" disabled={pending}>
          {pending ? "กำลังบันทึก..." : "บันทึกความเห็น"}
        </button>
      </form>
    </details>
  );
}

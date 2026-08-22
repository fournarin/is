"use client";

import { useActionState } from "react";

import { handOver, type HandoverState } from "@/app/work/actions";

const NOTHING_WRONG: HandoverState = { error: null };

/**
 * Handing over needs a note, and the button says so before it is pressed.
 *
 * ADR-025 asks for the note because without it the next shift finds an open
 * order and starts from step one. A dialog that refuses after the fact teaches
 * people to type a full stop; a button that will not arm until there is
 * something in the box asks for the sentence while they still remember it.
 */
// The prop is `workOrder` and not `ref`: React reserves that name, and a
// component taking one silently receives something else.
export function HandoverForm({ workOrder }: { workOrder: string }) {
  const [state, action, pending] = useActionState(handOver, NOTHING_WRONG);

  return (
    <details className="card">
      <summary>ส่งเวร</summary>
      <form action={action}>
        <input type="hidden" name="ref" value={workOrder} />
        {state.error !== null && (
          <p className="error" role="alert">
            {state.error}
          </p>
        )}
        <label className="field">
          <span>ทำถึงไหนแล้ว</span>
          <textarea
            name="note"
            rows={3}
            required
            placeholder="เช่น ถอดฝาครอบพัดลมแล้ว รออะไหล่ตลับลูกปืน"
          />
        </label>
        <button type="submit" disabled={pending}>
          {pending ? "กำลังส่งเวร..." : "ส่งเวรพร้อมโน้ตนี้"}
        </button>
      </form>
    </details>
  );
}

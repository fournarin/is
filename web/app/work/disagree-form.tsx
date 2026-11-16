"use client";

import { MessageSquareX, Send } from "lucide-react";
import { useActionState, useState } from "react";
import { Label, Radio, RadioGroup } from "react-aria-components";

import { type ObjectionState, disagree } from "@/app/work/actions";
import { plantTime } from "@/lib/display";

// Here and not in `actions.ts`: a `"use server"` file may only export async
// functions (slice 10.1).
const NOT_OBJECTED: ObjectionState = { error: null, recordedAt: null };

// The usual reasons, so a gloved hand taps instead of typing (REQ-T-13). The
// list is the design system's proposal (design/data/fixture.json
// NEW_disagree_reasons), to be confirmed with technicians; a tap only fills the
// text below, which the technician can still change, and the backend records
// the words as before (ADR-059).
const USUAL = ["มีงานอื่นต้องทำก่อน", "ไม่มีอะไหล่หรือเครื่องมือ", "ไม่ใช่ทักษะของฉัน"];

/**
 * Sits beside the reason, where somebody is already reading it.
 *
 * Not in a menu: ADR-005 says a system that cannot explain itself gets
 * overruled and then abandoned, and the objection belongs at the moment of
 * disbelief rather than three taps away from it.
 */
export function DisagreeForm({ workOrder, timezone }: { workOrder: string; timezone: string }) {
  const [state, action, pending] = useActionState(disagree, NOT_OBJECTED);
  const [reason, setReason] = useState("");

  if (state.recordedAt !== null) {
    return (
      <p className="callout is-ok v-note" role="status">
        <Send size={20} aria-hidden />
        <span>
          ส่งความเห็นแล้วเมื่อ {plantTime(state.recordedAt, timezone)} น. หัวหน้ากะจะเห็น ระหว่างนี้ลำดับงานยังเหมือนเดิม
        </span>
      </p>
    );
  }

  return (
    <details className="sheet">
      <summary>
        <MessageSquareX size={24} aria-hidden />
        ไม่เห็นด้วยว่าควรทำงานนี้ก่อน?
      </summary>
      <form action={action} style={{ marginTop: 8 }}>
        <input type="hidden" name="ref" value={workOrder} />
        {state.error !== null && (
          <p className="callout is-bad err" role="alert">
            {state.error}
          </p>
        )}
        <RadioGroup className="choices" value={USUAL.includes(reason) ? reason : null} onChange={setReason}>
          <Label className="muted">ทำไมไม่ควรเป็นงานนี้ก่อน · แตะเลือก หรือพิมพ์เอง</Label>
          {USUAL.map((one) => (
            <Radio key={one} value={one} className="v-choice">
              <span className="mk" aria-hidden />
              {one}
            </Radio>
          ))}
        </RadioGroup>
        <textarea
          name="reason"
          rows={3}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="เช่น MC-004 หยุดสายจริง งานนี้รอได้"
          aria-label="เหตุผล"
        />
        <button type="submit" className="btn pri" disabled={pending}>
          {pending ? "กำลังบันทึก..." : "ส่งความเห็นให้หัวหน้ากะ"}
        </button>
      </form>
    </details>
  );
}

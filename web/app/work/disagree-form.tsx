"use client";

import { MessageSquareX, Send } from "lucide-react";
import { type ReactNode, useActionState } from "react";
import { Label, Radio, RadioGroup } from "react-aria-components";

import { type ObjectionState, disagree } from "@/app/work/actions";
import { SheetClose } from "@/app/ui/v2/sheet-close";
import { plantTime } from "@/lib/display";

// Here and not in `actions.ts`: a `"use server"` file may only export async
// functions (slice 10.1).
const NOT_OBJECTED: ObjectionState = { error: null, recordedAt: null };

// The usual reasons, so a gloved hand taps instead of typing (REQ-T-13). The
// list is the design system's proposal (design/data/fixture.json
// NEW_disagree_reasons), to be confirmed with technicians; the tapped reason is
// sent with whatever is typed below it, and the backend records the words as
// before (ADR-059).
const USUAL = ["มีงานอื่นต้องทำก่อน", "ไม่มีอะไหล่หรือเครื่องมือ", "ไม่ใช่ทักษะของฉัน"];

/**
 * Why this job is ranked first, and the objection to it, in one sheet.
 *
 * The ranking reason opens the sheet, so somebody who disagrees reads the
 * system's case before writing theirs (ADR-005): a system that cannot explain
 * itself gets overruled and then abandoned. A tapped reason and the typed words
 * are sent together; the text box starts empty so nothing is said twice.
 */
export function DisagreeForm({
  workOrder,
  timezone,
  priorityReason,
}: {
  workOrder: string;
  timezone: string;
  priorityReason: ReactNode;
}) {
  const [state, action, pending] = useActionState(disagree, NOT_OBJECTED);

  if (state.recordedAt !== null) {
    return (
      <div className="rw info" role="status">
        <Send size={24} aria-hidden />
        <span className="t">
          ส่งความเห็นแล้วเมื่อ {plantTime(state.recordedAt, timezone)} น.
          <small>หัวหน้ากะจะเห็น ระหว่างนี้ลำดับงานยังเหมือนเดิม</small>
        </span>
      </div>
    );
  }

  return (
    <details className="sheet">
      <summary>
        <MessageSquareX size={24} aria-hidden />
        <span className="t">
          ไม่เห็นด้วยว่าควรทำงานนี้ก่อน?
          <small>ดูว่าทำไมต้องทำงานนี้ก่อน แล้วแตะเลือกเหตุผล</small>
        </span>
      </summary>
      <div className="panel">
      <div className="grab">
        <b>ทำไมต้องทำงานนี้ก่อน</b>
        <SheetClose />
      </div>
      <p>{priorityReason}</p>
      <form action={action} style={{ marginTop: 16 }}>
        <input type="hidden" name="ref" value={workOrder} />
        {state.error !== null && (
          <p className="callout is-bad err" role="alert">
            {state.error}
          </p>
        )}
        <RadioGroup className="choices" name="choice">
          <Label className="muted">ทำไมไม่ควรเป็นงานนี้ก่อน · แตะเลือก หรือพิมพ์เอง</Label>
          {USUAL.map((one) => (
            <Radio key={one} value={one} className="v-choice">
              <span className="mk" aria-hidden />
              {one}
            </Radio>
          ))}
        </RadioGroup>
        <textarea name="reason" rows={3} placeholder="เพิ่มเติม เช่น MC-004 หยุดสายจริง งานนี้รอได้" aria-label="เหตุผลเพิ่มเติม" />
        <button type="submit" className="btn pri" disabled={pending}>
          {pending ? "กำลังบันทึก..." : "ส่งความเห็นให้หัวหน้ากะ"}
        </button>
      </form>
      </div>
    </details>
  );
}

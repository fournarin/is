"use client";

import { ArrowRightLeft } from "lucide-react";
import { useActionState } from "react";

import type { LockContext } from "@/app/work/[ref]/close/close-form";
import { handOver, type HandoverState } from "@/app/work/actions";

const NOTHING_WRONG: HandoverState = { error: null };

const LOCK_LABELS = {
  released: "ปลดกุญแจของฉันแล้ว เครื่องคืนสู่การผลิต",
  still_locked: "ยังล็อกอยู่ (ระบุจุดและเหตุ)",
  not_isolated: "งานนี้ไม่ได้ตัดพลังงาน",
} as const;

/**
 * Handing over needs a note and an answer about locks, and the button says so
 * before it is pressed.
 *
 * ADR-025 asks for the note because without it the next shift finds an open
 * order and starts from step one. The lock answer is checked against the
 * register (REQ-H-06, ADR-135): a lock still on goes over with the job, in its
 * owner's name, and nobody is told the machine is free while it is not.
 *
 * The work order arrives as a hidden field rather than through `.bind()`: a
 * bound action that returns state never finishes its response on the
 * no-JavaScript path (see `actions.ts`).
 */
export function HandoverForm({ workOrder, locks, note }: { workOrder: string; locks: LockContext; note: string }) {
  const [state, action, pending] = useActionState(handOver, NOTHING_WRONG);
  const off = {
    released: locks.mine.length > 0 || !locks.hadMine,
    still_locked: locks.onJob.length === 0,
    not_isolated: locks.onJob.length > 0,
  };
  const why = {
    released:
      locks.mine.length > 0 ? "คนรับงานต้องใส่กุญแจของตัวเองก่อน" : !locks.hadMine ? "ทะเบียนไม่มีกุญแจของคุณในงานนี้" : null,
    still_locked: locks.onJob.length > 0 ? locks.onJob.join(", ") : "ทะเบียนไม่มีกุญแจที่ยังล็อกอยู่ในงานนี้",
    not_isolated: locks.onJob.length > 0 ? `ทะเบียนมีกุญแจ ${locks.onJob.join(", ")}` : null,
  };

  return (
    <form action={action}>
      <input type="hidden" name="ref" value={workOrder} />
      <input type="hidden" name="lock_question" value="1" />
      {state.error !== null && (
        <p className="callout is-bad err v-note" role="alert">
          {state.error}
        </p>
      )}

      <fieldset className="q">
        <legend className="qh">
          <span className="n">1</span>สถานะกุญแจ<span className="tag req">ต้องตอบ</span>
        </legend>
        <div className="g1">
          {(Object.keys(LOCK_LABELS) as (keyof typeof LOCK_LABELS)[]).map((answer) => (
            <label className="ch" key={answer}>
              <input
                type="radio"
                name="lock_state"
                value={answer}
                required
                disabled={off[answer]}
                defaultChecked={answer === "still_locked" && locks.mine.length > 0}
              />
              <span className="mk" aria-hidden />
              <span>
                {LOCK_LABELS[answer]}
                {why[answer] && <small>{why[answer]}</small>}
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {locks.mine.length > 0 && (
        <section className="q" aria-labelledby="gap-h">
          <h2 className="qh" id="gap-h">
            <span className="n">2</span>กุญแจต้องไม่มีช่วงว่าง
          </h2>
          <ol className="v-card gapfree" style={{ paddingTop: 0, paddingBottom: 0 }}>
            <li>
              <span className="k">1</span>
              <span>
                คนรับงานใส่กุญแจของตัวเองที่จุดเดียวกันก่อน
                <small>หัวหน้ากะเลือกคนรับ · ระหว่างนี้กุญแจของคุณยังอยู่ในทะเบียนในชื่อคุณ</small>
              </span>
            </li>
            <li>
              <span className="k">2</span>
              <span>
                {`จากนั้นคุณจึงปลดกุญแจ ${locks.mine.map((one) => one.split(" ")[0]).join(", ")} ของคุณ`}
                <small>ระบบยังไม่มีปุ่มส่งต่อกุญแจ ให้ปลดต่อหน้าหัวหน้ากะ</small>
              </span>
            </li>
          </ol>
        </section>
      )}

      <label className="q field">
        <span className="qh">
          <span className="n">{locks.mine.length > 0 ? 3 : 2}</span>โน้ตถึงคนถัดไป<span className="tag">แก้ได้</span>
        </span>
        <textarea name="note" rows={3} required defaultValue={note} placeholder="เช่น ถอดฝาครอบพัดลมแล้ว รออะไหล่ตลับลูกปืน" />
      </label>
      <p className="saved">ระบบเติมขั้นที่ทำถึงให้ · สถานะกุญแจขึ้นบรรทัดแรกของโน้ต</p>

      <div className="submit">
        <button type="submit" className="btn pri" disabled={pending}>
          <ArrowRightLeft size={24} aria-hidden />
          {pending ? "กำลังส่งต่อ..." : "ส่งต่องานให้หัวหน้ากะ"}
        </button>
      </div>
      <p className="saved">งานกลับเข้าคิว หัวหน้ากะจะส่งให้ช่างคนถัดไปพร้อมโน้ตนี้</p>
    </form>
  );
}

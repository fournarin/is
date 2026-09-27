"use client";

import { useActionState } from "react";

import { type DecisionState, approve, dismiss, sendBack } from "@/app/review/actions";

// Here rather than beside the actions: a `"use server"` file may only export
// async functions, and a constant next to the action that returns it is the
// mistake that shape invites (the same note is on the technician's screen).
const UNDECIDED: DecisionState = { error: null };

/**
 * The four decisions, and nothing that counts how long they took.
 *
 * There is no timer on this screen and there is nothing to build one from: the
 * API does not send the review clock (ADR-064). The time is recorded anyway,
 * server-side, between the open and the decision - which is the measurement the
 * report needs without putting a stopwatch in front of somebody reading
 * safety-critical text.
 *
 * "Approve" and "edit and approve" are one form and one action. They are one
 * decision: the second is the first carrying a diff, and splitting them is how
 * one of them ends up not storing it.
 */
export function Decisions({
  proposalId,
  steps,
  proposedSkill,
  proposedMinutes,
}: {
  proposalId: number;
  steps: string[];
  proposedSkill: string | null;
  proposedMinutes: number | null;
}) {
  const [approval, approveAction, approving] = useActionState(approve, UNDECIDED);
  const [returned, sendBackAction, sending] = useActionState(sendBack, UNDECIDED);
  const [dismissal, dismissAction, dismissing] = useActionState(dismiss, UNDECIDED);

  return (
    <>
      <section className="card">
        <h2>อนุมัติ</h2>
        <form action={approveAction}>
          <input type="hidden" name="proposal_id" value={proposalId} />
          {approval.error !== null && (
            <p className="error" role="alert">
              {approval.error}
            </p>
          )}

          {/* ADR-095: what the technician reads first. Every figure has to match
              the step it renders; the API refuses a rendering that changed one. */}
          <fieldset>
            <legend>คำแปลภาษาไทยสำหรับช่าง</legend>
            <p className="muted">
              ช่างจะเห็นคำแปลก่อน แล้วเห็นต้นฉบับจากคู่มือด้านล่าง ตัวเลขทุกตัว (แรงบิด ขนาด เวลา) ต้องตรงกับต้นฉบับ
              ขั้นไหนไม่แปลให้เว้นว่าง
            </p>
            {steps.map((text, index) => (
              <label className="field" key={index} style={{ padding: "0 0.75rem" }}>
                <span>
                  ขั้นที่ {index + 1} <small className="muted">· {text}</small>
                </span>
                <textarea name="thai" rows={2} placeholder="พิมพ์คำแปลภาษาไทย" />
              </label>
            ))}
          </fieldset>

          <details>
            <summary>แก้ข้อความก่อนอนุมัติ</summary>
            <p className="muted">
              แก้ได้เฉพาะข้อความ ที่มาของแต่ละขั้น (เอกสารและหน้า) ติดไปกับขั้นนั้นเสมอ
              และแก้ไม่ได้ ถ้าจะเพิ่มหรือลบขั้นตอน แปลว่าร่างนี้ผิด ให้ตีกลับ
            </p>
            {steps.map((text, index) => (
              <label className="field" key={index}>
                <span>ขั้นที่ {index + 1}</span>
                {/* The drafted wording travels with the form so the action can
                    tell an approval from an edit. Without it every approval
                    made through this form would arrive as an edit of every step
                    to itself, and the edit rate - a number in the report -
                    would count it (ADR-064). A hidden field can be tampered
                    with and nothing rests on it: the diff it produces is stored
                    beside the text that was actually approved. */}
                <input type="hidden" name="original" value={text} />
                <textarea name="step" rows={3} defaultValue={text} />
              </label>
            ))}
          </details>

          {/* The two figures a manual often does not state. Asked here because
              the approver is the only person who can say, and a value invented
              anywhere else would carry the authority of the manual and the
              provenance of nothing (ADR-037 section 8). */}
          <label className="field">
            <span>
              ทักษะที่ต้องใช้
              {proposedSkill !== null && <span className="muted"> · ร่างเสนอ {proposedSkill}</span>}
            </span>
            <input
              name="required_skill"
              defaultValue={proposedSkill ?? ""}
              required={proposedSkill === null}
              placeholder="เช่น robot_mechanical"
            />
          </label>
          <label className="field">
            <span>
              เวลาโดยประมาณ (นาที)
              {proposedMinutes !== null && <span className="muted"> · ร่างเสนอ {proposedMinutes}</span>}
            </span>
            <input
              name="estimated_minutes"
              type="number"
              min={1}
              defaultValue={proposedMinutes ?? ""}
              required={proposedMinutes === null}
            />
          </label>
          <label className="field">
            {/* ADR-025: a two-person job consumes twice the shift's capacity,
                and nothing drafts this, so leaving it at one quietly makes
                load_ratio read low. */}
            <span>ต้องใช้ช่างกี่คน</span>
            <input name="required_technicians" type="number" min={1} max={4} defaultValue={1} />
          </label>

          <button type="submit" disabled={approving}>
            {approving ? "กำลังบันทึก..." : "อนุมัติ"}
          </button>
        </form>
      </section>

      <section className="card">
        <h2>ตีกลับให้ร่างใหม่</h2>
        <form action={sendBackAction}>
          <input type="hidden" name="proposal_id" value={proposalId} />
          {returned.error !== null && (
            <p className="error" role="alert">
              {returned.error}
            </p>
          )}
          <label className="field">
            <span>ผิดตรงไหน (จะกลายเป็นคำถามของการร่างรอบหน้า)</span>
            <textarea
              name="note"
              rows={3}
              required
              placeholder="เช่น นี่คือขั้นตอนของสายพาน ไม่ใช่ของมอเตอร์ ให้ร่างจากหน้า 96"
            />
          </label>
          <button type="submit" className="quiet" disabled={sending}>
            {sending ? "กำลังส่ง..." : "ตีกลับ"}
          </button>
        </form>
      </section>

      <section className="card">
        <h2>ไม่เกี่ยว</h2>
        <form action={dismissAction}>
          <input type="hidden" name="proposal_id" value={proposalId} />
          {dismissal.error !== null && (
            <p className="error" role="alert">
              {dismissal.error}
            </p>
          )}
          <label className="field">
            {/* Required, and not by convention: the dismissals are what answer
                "why does this symptom still have no playbook when three people
                have looked at it" (ADR-038 section 6). */}
            <span>ทำไมใบนี้ไม่เกี่ยว</span>
            <textarea name="note" rows={2} required placeholder="เช่น ซ้ำกับ SYM-012 ที่อนุมัติไปแล้ว" />
          </label>
          <button type="submit" className="quiet" disabled={dismissing}>
            {dismissing ? "กำลังบันทึก..." : "ปิดใบนี้"}
          </button>
        </form>
      </section>
    </>
  );
}

import { NotYours, Shell } from "@/app/ui/shell";
import { plantTime } from "@/lib/display";
import { gaps } from "@/lib/overview";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { currentRound } from "@/lib/work";

/**
 * What the system cannot answer yet, and the button that starts answering it.
 *
 * An engineer's screen (ADR-093 moved it off the line overview): symptoms that
 * reached a ticket with no approved steps, drafts waiting for sign-off, and
 * steps served under a warning because their manual changed. Asking for a
 * draft is the engineer's alone - the worker behind it holds the one GPU
 * (ADR-029), and a button that always answers 403 would be a screen lying.
 */
export default async function GapsPage({
  searchParams,
}: {
  searchParams: Promise<{ drafting?: string; already?: string; error?: string }>;
}) {
  const account = await requireAccount();
  if (account.role !== "engineer" && account.role !== "supervisor") {
    return (
      <Shell account={account} current="/gaps">
        <NotYours home={homeFor(account.role)} what="หน้านี้เป็นของวิศวกร" />
      </Shell>
    );
  }
  const { drafting, already, error } = await searchParams;
  const [unanswered, round] = await Promise.all([gaps(), currentRound()]);
  const scheduled = unanswered.pm_without_steps ?? [];

  return (
    <Shell account={account} current="/gaps">
      <h1>อาการที่ยังไม่มีขั้นตอนซ่อม</h1>
      <p className="muted">
        ใบงานของอาการเหล่านี้ถึงมือช่างโดยไม่มีขั้นตอน ระบบร่างขั้นตอนจากคู่มือให้เองเมื่ออาการเกิดครั้งแรก
        ร่างจะไปรอที่หน้า “อนุมัติขั้นตอน” วิศวกรตรวจเทียบกับหน้าคู่มือแล้วอนุมัติก่อนถึงมือช่าง
      </p>

      {drafting !== undefined && (
        <p className="recorded">
          {already === undefined
            ? `✓ สั่งร่าง ${drafting} แล้ว ร่างจะไปรออยู่ที่หน้า "อนุมัติขั้นตอน" ภายในไม่กี่นาที`
            : already === "review"
              ? `${drafting} มีร่างรออนุมัติอยู่แล้ว ไม่ได้สั่งซ้ำ`
              : `${drafting} กำลังร่างอยู่แล้ว ไม่ได้สั่งซ้ำ`}
        </p>
      )}
      {error !== undefined && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {unanswered.no_playbook.rows.length === 0 ? (
        <div className="card empty">
          <span className="icon" aria-hidden="true">
            🎉
          </span>
          <p>ทุกอาการที่เคยเกิดมีขั้นตอนซ่อมแล้ว</p>
        </div>
      ) : (
        unanswered.no_playbook.rows.map((row) => (
          <article className="card" key={`${row.symptom_code}-${row.machine_model}`}>
            <h2 style={{ marginTop: 0 }}>{row.title ?? row.symptom_code}</h2>
            <p className="muted">
              เครื่องรุ่น {row.machine_model} · รหัส {row.symptom_code} · เกิดแล้ว {row.findings} ครั้ง
            </p>
            {row.proposals_waiting > 0 ? (
              <p className="pending">
                {/* A "not found" is a decision, not a draft (fourth trial). */}
                {row.proposals_waiting - (row.proposals_not_found ?? 0) > 0
                  ? `มีร่างรอวิศวกรดู ${row.proposals_waiting - (row.proposals_not_found ?? 0)} ฉบับ (ที่หน้า “อนุมัติขั้นตอน”)`
                  : "ระบบค้นคู่มือแล้วไม่พบเรื่องนี้ รอวิศวกรตัดสินใจที่หน้า “อนุมัติขั้นตอน”"}
              </p>
            ) : (
              account.role === "engineer" && (
                <DraftRequest symptomCode={row.symptom_code} machineModel={row.machine_model} title={row.title} />
              )
            )}
          </article>
        ))
      )}

      {/* Fourth trial, finding 11: scheduled work raises no symptom, so a PM
          task with no steps never reached the list above. */}
      <h2>งานบำรุงรักษาตามรอบ (PM) ที่ยังไม่มีขั้นตอน ({scheduled.length})</h2>
      {scheduled.length === 0 ? (
        <p className="muted">ไม่มี</p>
      ) : (
        scheduled.map((row) => (
          <article className="card" key={`${row.symptom_code}-${row.machine_model}`}>
            <h2 style={{ marginTop: 0 }}>{row.title ?? row.symptom_code}</h2>
            <p className="muted">
              เครื่องรุ่น {row.machine_model} · รหัส {row.symptom_code} · เครื่อง {row.machines.join(", ")}
            </p>
            {row.proposals_waiting > 0 ? (
              <p className="pending">มีร่างรอวิศวกรดูที่หน้า “อนุมัติขั้นตอน”</p>
            ) : (
              account.role === "engineer" && (
                <DraftRequest symptomCode={row.symptom_code} machineModel={row.machine_model} title={row.title} />
              )
            )}
          </article>
        ))
      )}

      <h2>ร่างที่รอวิศวกรอนุมัติ ({unanswered.awaiting_review.count})</h2>
      {unanswered.awaiting_review.rows.length === 0 ? (
        <p className="muted">ไม่มี</p>
      ) : (
        <ul className="gaps card">
          {unanswered.awaiting_review.rows.map((row) => (
            <li key={row.machine_model}>
              <strong>{row.machine_model}</strong> · {row.waiting - (row.not_found ?? 0)} ฉบับรออนุมัติ
              {(row.not_found ?? 0) > 0 && ` · ${row.not_found} เรื่องที่คู่มือไม่มีคำตอบ`} · เก่าสุด{" "}
              {plantTime(row.oldest, round.timezone)} น.
            </li>
          ))}
        </ul>
      )}

      <h2>ขั้นตอนที่คู่มือถูกเปลี่ยน ต้องตรวจใหม่ ({unanswered.manual_changed.count})</h2>
      {unanswered.manual_changed.rows.length === 0 ? (
        <p className="muted">ไม่มี</p>
      ) : (
        <ul className="gaps card">
          {unanswered.manual_changed.rows.map((row) => (
            <li key={`${row.symptom_code}-${row.machine_model}`}>
              <strong>{row.title ?? row.symptom_code}</strong> · {row.machine_model} · ฉบับที่ {row.revision}
              {row.review_reason !== null && <span className="muted"> · {row.review_reason}</span>}
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}

/** Ask for a draft of one symptom or PM task (ADR-003, ADR-040). */
function DraftRequest({
  symptomCode,
  machineModel,
  title,
}: {
  symptomCode: string;
  machineModel: string;
  title: string | null;
}) {
  return (
    <details>
      <summary>📝 ขอร่างใหม่</summary>
      <form method="post" action="/overview/draft">
        <input type="hidden" name="symptom_code" value={symptomCode} />
        <input type="hidden" name="machine_model" value={machineModel} />
        <label className="field">
          <span>คำที่ใช้ค้นคู่มือ</span>
          <input type="text" name="question" required defaultValue={title ?? ""} />
          {/* The rule's own words are the default, and drafting also
              checks every page against them (ADR-121). The old hint
              asked for figures, and "85 องศา" typed for the safety
              interlock drafted the belt-motor page. */}
          <small className="muted">
            ระบบใส่ชื่ออาการไว้ให้แล้ว เติมคำที่คู่มือน่าจะใช้ได้ ขั้นตอนที่ร่างต้องเกี่ยวกับอาการนี้เสมอ
            ถ้าคู่มือไม่มีเรื่องนี้ ระบบจะบอกว่าไม่พบ ไม่เดา
          </small>
        </label>
        <button type="submit">ขอร่าง</button>
      </form>
    </details>
  );
}

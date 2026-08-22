import Link from "next/link";

import { startWork } from "@/app/work/actions";
import { DisagreeForm } from "@/app/work/disagree-form";
import { bandFor, seenLine } from "@/lib/display";
import { ROLE_NAMES, requireAccount } from "@/lib/session";
import { currentRound, myWork, type Ticket } from "@/lib/work";

/**
 * One job, not a menu.
 *
 * The scheduler has already decided the order, and offering a list would let a
 * technician take the easy one first - which is exactly what the load gate
 * exists to prevent (ADR-011, ADR-058). What is queued behind it is shown, so
 * the shift is not a black box, and it is not selectable.
 */
export default async function WorkPage() {
  const account = await requireAccount();
  if (account.role !== "technician") {
    return (
      <>
        <h1>งานของช่าง</h1>
        <p className="card">
          หน้านี้เป็นของช่าง บัญชีนี้เป็น{ROLE_NAMES[account.role]} — งานที่ระบบจัดให้จะไม่ปรากฏที่นี่
        </p>
        <p>
          <Link href="/">กลับหน้าแรก</Link>
        </p>
      </>
    );
  }

  const round = await currentRound();
  const mine = await myWork(round, account.user);

  if (mine.length === 0) {
    return (
      <>
        <h1>งานของคุณ</h1>
        <p className="card">
          ตอนนี้ยังไม่มีงานที่ถูกจัดให้คุณ รอบถัดไปคำนวณเมื่อ {round.summary}
        </p>
        <p>
          <Link href="/">กลับหน้าแรก</Link>
        </p>
      </>
    );
  }

  const [now, ...next] = mine as [Ticket, ...Ticket[]];
  const band = bandFor(now);
  const seen = seenLine(now, round.timezone);
  const inProgress = now.status === "in_progress";

  return (
    <>
      <div className="who">
        <span>
          งานของคุณ
          <span className="muted"> · งานที่ 1 จาก {mine.length}</span>
        </span>
        <Link href="/">หน้าแรก</Link>
      </div>

      <section className={`card job ${band.tone}`}>
        <div className="screen-head">
          <h1>
            {band.label} · {now.machine_id}
          </h1>
          <span className="muted">{now.ref}</span>
        </div>

        {/* Written by the backend when the job was created, never here. */}
        <p className="reason">{now.reason}</p>
        {seen !== null && <p className="muted">{seen}</p>}

        {now.playbook_warning !== null && (
          <p className="warning">
            คู่มือถูกเปลี่ยน ขั้นตอนชุดนี้รออนุมัติใหม่ — ตรวจกับคู่มือก่อนลงมือ
          </p>
        )}

        <h2>ทำไมงานนี้ก่อน</h2>
        {now.priority_reason === "" ? (
          <p className="muted">ยังไม่มีรอบไหนจัดอันดับงานนี้</p>
        ) : (
          <p>{now.priority_reason}</p>
        )}
        <DisagreeForm workOrder={now.ref} timezone={round.timezone} />
      </section>

      {inProgress ? (
        <Link className="button-link" href={`/work/${encodeURIComponent(now.ref)}/steps`}>
          ทำต่อ
        </Link>
      ) : (
        <form action={startWork.bind(null, now.ref)}>
          <button type="submit">เริ่มงาน</button>
        </form>
      )}

      {next.length > 0 && (
        <details className="card">
          <summary>ถัดไป ({next.length})</summary>
          <ul className="next">
            {next.map((one) => (
              <li key={one.ref}>
                <strong>{one.machine_id}</strong> · {bandFor(one).label}
                <br />
                <span className="muted">{one.reason}</span>
              </li>
            ))}
          </ul>
          <p className="muted">
            ลำดับนี้ระบบจัดไว้แล้ว เลือกเองไม่ได้ — ปิดงานปัจจุบันแล้วงานถัดไปจะขึ้นมาเอง
          </p>
        </details>
      )}
    </>
  );
}

import Link from "next/link";

import { startWork } from "@/app/work/actions";
import { DisagreeForm } from "@/app/work/disagree-form";
import { NotYours, Shell } from "@/app/ui/shell";
import { bandFor, minutesText, seenLine } from "@/lib/display";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { currentRound, myWork, proposals, type Ticket } from "@/lib/work";

/**
 * One job, not a menu - the way a ride-hailing app hands a driver one trip
 * (ADR-093).
 *
 * The scheduler has already decided the order, and offering a list would let a
 * technician take the easy one first, which is what the load gate exists to
 * prevent (ADR-011, ADR-058). What is queued behind it is shown and is not
 * selectable. Every sentence on it was written by the backend (ADR-005).
 */
export default async function WorkPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const account = await requireAccount();
  const { error } = await searchParams;
  if (account.role !== "technician") {
    return (
      <Shell account={account} current="/work">
        <NotYours home={homeFor(account.role)} what="หน้านี้เป็นหน้างานของช่าง" />
      </Shell>
    );
  }

  const [round, mine] = await Promise.all([currentRound(), myWork()]);

  if (mine.length === 0) {
    // "Nothing yet" and "waiting for your shift lead" are different sentences
    // (ADR-005, ADR-071 §7).
    const waiting = (await proposals()).filter((one) => one.assignees.includes(account.user));
    return (
      <Shell account={account} current="/work">
        <div className="card empty">
          <span className="icon" aria-hidden="true">
            {waiting.length > 0 ? "⏳" : "☕"}
          </span>
          <h1>{waiting.length > 0 ? "มีงานรอหัวหน้ากะยืนยัน" : "ตอนนี้ยังไม่มีงาน"}</h1>
          <p>
            {waiting.length > 0
              ? `ระบบจัดงานให้คุณแล้ว ${waiting.length} งาน พอหัวหน้ากะยืนยัน งานจะขึ้นที่หน้านี้`
              : "เมื่อมีงานใหม่ จะขึ้นที่หน้านี้ทันที"}
          </p>
          <p className="muted">{round.summary}</p>
          <Link className="button-link quiet" href="/report">
            📣 เจอเครื่องเสีย? แจ้งซ่อม
          </Link>
        </div>
      </Shell>
    );
  }

  const [now, ...next] = mine as [Ticket, ...Ticket[]];
  const band = bandFor(now);
  const seen = seenLine(now, round.timezone);
  const inProgress = now.status === "in_progress";
  const hasSteps = now.steps.length > 0;

  return (
    <Shell account={account} current="/work">
      {error !== undefined && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <p className="muted">
        งานที่ 1 จาก {mine.length} · ใบงาน {now.ref}
      </p>

      <section className={`card job ${band.tone}`}>
        <div className="job-head">
          <span className={`pill ${band.tone}`}>{band.label}</span>
          {inProgress && <span className="pill">กำลังทำ</span>}
        </div>
        <p className="machine">
          {now.machine_id}
          {now.station !== null && <span className="muted"> · {now.station}</span>}
        </p>

        {/* Written by the backend when the job was created, never here. */}
        <p className="symptom reason">{now.reason}</p>
        {seen !== null && <p className="muted">{seen}</p>}
        {/* The reason is written once (ADR-005); the machine moves on. A
            forecast overtaken by the crossing it predicted says so here. */}
        {now.recurrence?.status === "superseded" && (
          <p className="warning">⚠️ สถานะล่าสุด: อาการนี้เกินเกณฑ์แล้ว ไม่ใช่แค่คาดการณ์ ให้ถือเป็นงานด่วน</p>
        )}

        <div className="facts">
          <div className="fact">
            <span className="label">เวลาโดยประมาณ</span>
            <span className="value">
              {minutesText(now.estimated_minutes)}
              {now.estimate_is_fallback && " (ค่าประมาณคร่าว ๆ)"}
            </span>
          </div>
          <div className="fact">
            <span className="label">ทักษะที่ใช้</span>
            <span className="value">{now.required_skill_name ?? "ทั่วไป"}</span>
          </div>
          <div className="fact">
            <span className="label">จำนวนช่าง</span>
            <span className="value">{now.required_technicians} คน</span>
          </div>
          {now.tools.length > 0 && (
            <div className="fact" style={{ gridColumn: "1 / -1" }}>
              <span className="label">เครื่องมือที่ต้องเตรียม</span>
              <span className="value">{now.tools.join(" · ")}</span>
            </div>
          )}
          <div className="fact">
            <span className="label">ขั้นตอนซ่อม</span>
            <span className="value">
              {hasSteps ? `${now.steps.length} ขั้นตอน` : "ยังไม่มี · ดูคู่มือ"}
            </span>
          </div>
        </div>

        {now.handover_note && (
          <p className="warning">↪ ช่างคนก่อนทำไว้ถึงตรงนี้: {now.handover_note}</p>
        )}

        {now.playbook_warning !== null && (
          <p className="warning">
            ⚠️ คู่มือของเครื่องนี้เพิ่งถูกเปลี่ยน ขั้นตอนชุดนี้รอวิศวกรตรวจใหม่ ให้เทียบกับคู่มือก่อนลงมือ
          </p>
        )}

        <div className="why">
          <span className="label">ทำไมต้องทำงานนี้ก่อน</span>
          {now.priority_reason === "" ? (
            <p className="reason muted">ยังไม่ได้จัดลำดับ</p>
          ) : (
            <p className="reason">{now.priority_reason}</p>
          )}
        </div>

        {inProgress ? (
          <Link className="button-link big" href={`/work/${encodeURIComponent(now.ref)}/steps`}>
            ทำต่อ →
          </Link>
        ) : (
          <form action={startWork.bind(null, now.ref)}>
            <button type="submit" className="big ok">
              ▶ รับงานและเริ่มทำ
            </button>
          </form>
        )}

        <DisagreeForm workOrder={now.ref} timezone={round.timezone} />
      </section>

      <p className="no-print">
        <Link href={`/work/${encodeURIComponent(now.ref)}/print`}>🖨️ พิมพ์ใบงาน</Link>
      </p>

      {next.length > 0 && (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>งานถัดไปของคุณ ({next.length})</h2>
          <ul className="next">
            {next.map((one) => (
              <li key={one.ref}>
                <span className={`pill ${bandFor(one).tone}`}>{bandFor(one).label}</span>{" "}
                <strong>{one.machine_id}</strong>
                <br />
                <span className="muted">{one.reason}</span>
              </li>
            ))}
          </ul>
          <p className="muted">ระบบเรียงลำดับไว้แล้ว ปิดงานนี้แล้วงานถัดไปจะขึ้นมาเอง</p>
        </section>
      )}
    </Shell>
  );
}

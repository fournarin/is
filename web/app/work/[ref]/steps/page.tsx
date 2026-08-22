import Link from "next/link";
import { notFound } from "next/navigation";

import { HandoverForm } from "@/app/work/[ref]/steps/handover-form";
import { requireAccount } from "@/lib/session";
import { ticket } from "@/lib/work";

/**
 * One step at a time, because the other hand is holding a tool.
 *
 * The steps come from `playbook_snapshot` by way of the ticket endpoint, never
 * from the playbook table: an order has to show what it instructed when it was
 * issued, and re-approval overwrites the served row (ADR-018).
 */
export default async function StepsPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string }>;
  searchParams: Promise<{ step?: string }>;
}) {
  await requireAccount();
  const { ref } = await params;
  const { step } = await searchParams;

  const job = await ticket(decodeURIComponent(ref));
  const total = job.steps.length;

  if (total === 0) {
    return (
      <>
        <div className="who">
          <span>
            {job.machine_id} <span className="muted">{job.ref}</span>
          </span>
          <Link href="/work">งานของคุณ</Link>
        </div>
        <h1>ยังไม่มีขั้นตอนสำหรับงานนี้</h1>
        {/* Principle 5: saying so beats inventing a procedure. */}
        <p className="card">
          ระบบยังไม่มี playbook ที่อนุมัติแล้วสำหรับอาการนี้ ให้ดูคู่มือของเครื่องหรือถามวิศวกร
          อย่าเดาขั้นตอน
        </p>
        <p>{job.reason}</p>
        <Link className="button-link quiet" href={`/work/${encodeURIComponent(job.ref)}/close`}>
          ปิดงาน
        </Link>
        <HandoverForm workOrder={job.ref} />
      </>
    );
  }

  // 1-based, matching what the screen says. Anything outside the playbook is a
  // typed URL rather than a link this app produced.
  const at = Number(step ?? "1");
  if (!Number.isInteger(at) || at < 1 || at > total) {
    notFound();
  }
  const current = job.steps[at - 1]!;

  return (
    <>
      <div className="who">
        <span>
          <Link href="/work">‹ {job.machine_id}</Link>
        </span>
        <span className="muted">
          {job.ref} · ขั้นที่ {at} จาก {total}
        </span>
      </div>

      {job.playbook_warning !== null && (
        <p className="warning">คู่มือถูกเปลี่ยน ขั้นตอนชุดนี้รออนุมัติใหม่ — ตรวจกับคู่มือก่อนลงมือ</p>
      )}

      <section className="card step">
        <p className="step-text">{current.text}</p>
        <p className="muted">
          {/* Opens the manual at that page through this server, which forwards
              the range request - not a whole-volume download (ADR-019, ADR-058). */}
          <a
            href={`/manual/${encodeURIComponent(current.source_doc)}#page=${current.page}`}
            target="_blank"
            rel="noreferrer"
          >
            เปิดคู่มือหน้า {current.page}
          </a>
        </p>
      </section>

      <div className="step-nav">
        {at > 1 ? (
          <Link className="button-link quiet" href={`?step=${at - 1}`}>
            ย้อนกลับ
          </Link>
        ) : (
          <span />
        )}
        {at < total ? (
          <Link className="button-link" href={`?step=${at + 1}`}>
            ถัดไป
          </Link>
        ) : (
          <span className="muted done">ขั้นตอนสุดท้าย</span>
        )}
      </div>

      <Link className="button-link quiet" href={`/work/${encodeURIComponent(job.ref)}/close`}>
        ปิดงาน
      </Link>

      <HandoverForm workOrder={job.ref} />
    </>
  );
}

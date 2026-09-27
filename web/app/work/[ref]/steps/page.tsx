import Link from "next/link";
import { notFound } from "next/navigation";

import { Shell } from "@/app/ui/shell";
import { HandoverForm } from "@/app/work/[ref]/steps/handover-form";
import { requireAccount } from "@/lib/session";
import { ticket } from "@/lib/work";

/**
 * One step at a time, because the other hand is holding a tool - with the whole
 * checklist underneath, so nobody loses their place (ADR-093).
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
  const account = await requireAccount();
  const { ref } = await params;
  const { step } = await searchParams;

  const job = await ticket(decodeURIComponent(ref));
  const total = job.steps.length;
  const close = `/work/${encodeURIComponent(job.ref)}/close`;

  if (total === 0) {
    return (
      <Shell account={account} current="/work">
        <p>
          <Link href="/work">‹ กลับไปที่ใบงาน</Link>
        </p>
        <section className="card job normal">
          <p className="machine">{job.machine_id}</p>
          <h1>ยังไม่มีขั้นตอนซ่อมที่อนุมัติแล้วสำหรับอาการนี้</h1>
          {/* Principle 5: saying so beats inventing a procedure. */}
          <p>ให้ดูคู่มือของเครื่อง หรือโทรถามวิศวกร อย่าเดาขั้นตอนเอง</p>
          <p className="muted">{job.reason}</p>
        </section>
        <Link className="button-link big ok" href={close}>
          ✓ ทำเสร็จแล้ว ปิดงาน
        </Link>
        <HandoverForm workOrder={job.ref} />
      </Shell>
    );
  }

  // 1-based, matching what the screen says. Anything outside the playbook is a
  // typed URL rather than a link this app produced.
  const at = Number(step ?? "1");
  if (!Number.isInteger(at) || at < 1 || at > total) {
    notFound();
  }
  const current = job.steps[at - 1]!;
  const last = at === total;

  return (
    <Shell account={account} current="/work">
      <div className="who">
        <Link href="/work">‹ {job.machine_id}</Link>
        <span className="muted">ใบงาน {job.ref}</span>
      </div>

      <div className="progress" aria-hidden="true">
        <span style={{ width: `${Math.round((at / total) * 100)}%` }} />
      </div>

      {job.playbook_warning !== null && (
        <p className="warning">⚠️ คู่มือเพิ่งถูกเปลี่ยน ขั้นตอนชุดนี้รอวิศวกรตรวจใหม่ ให้เทียบกับคู่มือก่อน</p>
      )}

      <section className="card step">
        <span className="step-number">
          ขั้นที่ {at} จาก {total}
        </span>
        <p className="step-text">{current.text_th ?? current.text}</p>
        {/* The manual's own words stay on screen under the Thai: the page
            citation proves those, and a technician can check one against the
            other (ADR-095). */}
        {current.text_th !== null && (
          <p className="muted">
            ต้นฉบับจากคู่มือ: <span lang="en">{current.text}</span>
          </p>
        )}
        {/* Opens the manual at that page through this server, which forwards
            the range request - not a whole-volume download (ADR-019, ADR-058). */}
        <a
          className="button-link quiet"
          href={`/manual/${encodeURIComponent(current.source_doc)}#page=${current.page}`}
          target="_blank"
          rel="noreferrer"
        >
          📖 เปิดคู่มือหน้า {current.page}
        </a>
      </section>

      <div className="step-nav">
        {at > 1 ? (
          <Link className="button-link quiet" href={`?step=${at - 1}`}>
            ← ย้อน
          </Link>
        ) : (
          <span />
        )}
        {last ? (
          <Link className="button-link ok" href={close}>
            ✓ ครบทุกขั้น ปิดงาน
          </Link>
        ) : (
          <Link className="button-link" href={`?step=${at + 1}`}>
            ทำขั้นนี้แล้ว ถัดไป →
          </Link>
        )}
      </div>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>ขั้นตอนทั้งหมด</h2>
        <ol className="checklist">
          {job.steps.map((one, index) => (
            <li
              key={index}
              className={index + 1 < at ? "passed" : index + 1 === at ? "current" : undefined}
            >
              <span>
                <Link href={`?step=${index + 1}`} style={{ color: "inherit", textDecoration: "none" }}>
                  {one.text_th ?? one.text}
                </Link>
                <br />
                <span className="muted">คู่มือหน้า {one.page}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>

      {!last && (
        <p>
          <Link href={close}>ทำเสร็จก่อนครบทุกขั้น? ปิดงาน</Link>
        </p>
      )}
      <HandoverForm workOrder={job.ref} />
    </Shell>
  );
}

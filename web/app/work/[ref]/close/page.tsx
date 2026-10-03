import { NotThere, Shell } from "@/app/ui/shell";
import Link from "next/link";

import { CloseForm } from "@/app/work/[ref]/close/close-form";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { ticketAt } from "@/lib/work";

/**
 * How the job ended, in two taps.
 *
 * Anything heavier is not filled in truthfully at the end of a shift, and the
 * fields here are the ones the feedback loops need rather than the ones a form
 * would naturally grow: how it ended (ADR-022's only false-alarm signal is one
 * of the four), and how much of the elapsed time was not repair (ADR-006).
 */
export default async function ClosePage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string }>;
  searchParams: Promise<{ error?: string; reached?: string }>;
}) {
  const account = await requireAccount();
  const { ref } = await params;
  const { error, reached } = await searchParams;
  const job = await ticketAt(decodeURIComponent(ref));
  if (job === null) {
    return (
      <Shell account={account} current="/work">
        <NotThere home={homeFor(account.role)} what="ไม่พบใบงานนี้" />
      </Shell>
    );
  }

  return (
    <Shell account={account} current="/work">
      <div className="who">
        <span>
          <Link href={`/work/${encodeURIComponent(job.ref)}/steps`}>‹ {job.machine_id}</Link>
        </span>
        <span className="muted">{job.ref}</span>
      </div>

      <h1>✓ ปิดงาน</h1>
      <p className="muted">{job.reason}</p>
      {job.eta_text && <p className="muted">{job.eta_text}</p>}

      {/* The path with no JavaScript comes back here with the reason in the
          URL, because a redirect cannot carry state any other way. It is the
          API's own sentence and is shown as written. */}
      {error !== undefined && error !== "" && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {/* Closing from step 1 of 6 said nothing about the five never reached
          (fourth trial). Not a refusal - the technician may have done them
          from memory, or found the fault was elsewhere - but said, so that a
          close is a decision rather than a slip. */}
      {(() => {
        const at = Number(reached);
        const left = job.steps.length - at;
        return Number.isInteger(at) && at >= 1 && left > 0 ? (
          <p className="warning">
            คุณเปิดถึงขั้นที่ {at} จาก {job.steps.length} ยังเหลืออีก {left} ขั้นที่ยังไม่ได้เปิดดู
            ถ้าทำครบแล้วหรือไม่ต้องทำ ปิดงานได้เลย
          </p>
        ) : null;
      })()}

      <CloseForm workOrder={job.ref} />

      {/* Never asked for, and saying so is the point: a technician who thinks
          the clock is a grade stops pressing start (ADR-058, ADR-006). */}
      <p className="muted">
        ไม่ต้องกรอกเวลาที่ใช้ ระบบนับจากตอนกด &ldquo;รับงานและเริ่มทำ&rdquo; ให้เอง
      </p>
    </Shell>
  );
}

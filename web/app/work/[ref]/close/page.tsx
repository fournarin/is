import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { NotThere, Shell } from "@/app/ui/shell";
import { Clock, PhoneFrame, Plate, Th } from "@/app/ui/v2/frame";
import { LockBar } from "@/app/ui/v2/signs";
import { CloseForm, type LockContext } from "@/app/work/[ref]/close/close-form";
import { plantTime } from "@/lib/display";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { currentRound, ticketAt } from "@/lib/work";

/**
 * How the job ended, what held it up, and what is still locked (REQ-H-06).
 *
 * Anything heavier is not filled in truthfully at the end of a shift, and the
 * fields here are the ones the feedback loops need rather than the ones a form
 * would naturally grow: how it ended (ADR-022's only false-alarm signal is one
 * of the four), how much of the elapsed time was not repair (ADR-006), and the
 * one answer that can hurt somebody if it is wrong - the locks, checked against
 * the register (ADR-135).
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
  const [job, round] = await Promise.all([ticketAt(decodeURIComponent(ref)), currentRound()]);
  if (job === null) {
    return (
      <Shell account={account} current="/work">
        <NotThere home={homeFor(account.role)} what="ไม่พบใบงานนี้" />
      </Shell>
    );
  }

  const total = job.steps.length;
  // `reached` is how many steps are done: the step page sends the one before the
  // step it was on, and the last step sends all of them (fourth trial, trial 5).
  const given = Number(reached);
  const done = Number.isInteger(given) && given >= 0 ? Math.min(given, total) : Math.max((job.step_reached ?? 1) - 1, 0);
  const left = total - done;
  const resume = Math.min(done + 1, Math.max(total, 1));
  const back = `/work/${encodeURIComponent(job.ref)}/steps${total > 0 ? `?step=${resume}` : ""}`;
  const backLabel = total > 0 ? `ยังไม่ปิด กลับไปขั้น ${resume}` : "ยังไม่ปิด กลับไปที่ใบงาน";

  const onJob = (job.locks ?? []).filter((one) => one.work_order_ref === job.ref);
  const said = (one: NonNullable<typeof job.locks>[number]) => `${one.lock_no} ที่ ${one.point_id} ใส่ ${plantTime(one.applied_at, round.timezone)} น.`;
  const mine = onJob.filter((one) => one.owner === account.user);
  const restore = job.steps.findIndex(
    (step, index) => index >= done && step.kind === "restore" && (step.isolation_points ?? []).some((point) => mine.some((one) => one.point_id === point.point_id)),
  );
  const locks: LockContext = {
    mine: mine.map(said),
    mineShort: mine.map((one) => `${one.lock_no} ยังล็อก ${one.point_id}`),
    onJob: onJob.map(said),
    onMachine: (job.locks ?? []).map(said),
    otherJobs: (job.locks ?? []).filter((one) => one.work_order_ref !== job.ref).map((one) => `${one.owner_name} ที่ ${one.point_id} (${one.work_order_ref})`),
    hadMine: (job.confirmations ?? []).some((one) => one.item === "locked" && one.by === account.user),
    anybodyLocked: (job.confirmations ?? []).some((one) => one.item === "locked"),
    restoreLeft: restore >= 0 ? `ขั้น ${restore + 1} “${job.steps[restore]!.text_th ?? job.steps[restore]!.text}”` : null,
  };
  const symptom = job.title ? job.title.replace(job.machine_id, "").trim() : job.reason;

  const top = (
    <>
      <Link className="back" href={back}>
        <ArrowLeft size={24} aria-hidden />
        {total > 0 ? `ขั้น ${resume}` : "งาน"}
      </Link>
      <span className="anc">ปิดงาน</span>
      <Clock now={new Date()} timezone={round.timezone} date={false} />
    </>
  );

  return (
    <PhoneFrame top={top}>
      <LockBar locks={job.locks ?? []} you={account.user} timezone={round.timezone} />
      <Plate job={job} lamps={null} sub={<span className="w">{job.ref}</span>} />
      <p className="when" style={{ marginTop: 16 }}>
        <Th>{symptom}</Th>
        {total > 0 && (
          <span style={{ display: "block" }}>
            {`ทำแล้ว ${done} จาก ${total} ขั้น`}
            {left > 0 && <span className="muted" style={{ fontWeight: 400 }}>{` · ยังเหลืออีก ${left} ขั้น (${done + 1}${left > 1 ? `–${total}` : ""})`}</span>}
          </span>
        )}
      </p>

      {/* The path with no JavaScript comes back here with the reason in the
          URL, because a redirect cannot carry state any other way. It is the
          API's own sentence and is shown as written. */}
      {error !== undefined && error !== "" && (
        <p className="callout is-bad err v-note" role="alert">
          <Th>{error}</Th>
        </p>
      )}

      <CloseForm
        workOrder={job.ref}
        locks={locks}
        back={back}
        backLabel={backLabel}
        stepsLeft={job.steps.slice(done).map((step, index) => `ขั้น ${done + index + 1} · ${step.text_th ?? step.text}`)}
      />

      {/* Never asked for, and saying so is the point: a technician who thinks
          the clock is a grade stops pressing start (ADR-058, ADR-006). */}
      <p className="saved">ไม่ต้องกรอกเวลาที่ใช้ ระบบนับจากตอนกด &ldquo;รับงานและเริ่มทำ&rdquo; ให้เอง</p>
    </PhoneFrame>
  );
}

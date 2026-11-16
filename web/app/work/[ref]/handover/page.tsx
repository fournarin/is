import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { NotThere, Shell } from "@/app/ui/shell";
import { Clock, PhoneFrame, Plate, Th } from "@/app/ui/v2/frame";
import { LockBar } from "@/app/ui/v2/signs";
import { HandoverForm } from "@/app/work/[ref]/handover/handover-form";
import type { LockContext } from "@/app/work/[ref]/close/close-form";
import { plantTime } from "@/lib/display";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { currentRound, ticketAt } from "@/lib/work";

/** Putting the job down for the next person: how far it got, and what is still locked (ADR-025, ADR-135). */
export default async function HandoverPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string }>;
  searchParams: Promise<{ reached?: string }>;
}) {
  const account = await requireAccount();
  const { ref } = await params;
  const { reached } = await searchParams;
  const [job, round] = await Promise.all([ticketAt(decodeURIComponent(ref)), currentRound()]);
  if (job === null) {
    return (
      <Shell account={account} current="/work">
        <NotThere home={homeFor(account.role)} what="ไม่พบใบงานนี้" />
      </Shell>
    );
  }
  const total = job.steps.length;
  const given = Number(reached);
  const at = Number.isInteger(given) && given >= 1 ? Math.min(given, total) : (job.step_reached ?? 1);
  const back = `/work/${encodeURIComponent(job.ref)}/steps${total > 0 ? `?step=${at}` : ""}`;
  const onJob = (job.locks ?? []).filter((one) => one.work_order_ref === job.ref);
  const said = (one: NonNullable<typeof job.locks>[number]) => `${one.lock_no} ที่ ${one.point_id} ใส่ ${plantTime(one.applied_at, round.timezone)} น.`;
  const mine = onJob.filter((one) => one.owner === account.user);
  const locks: LockContext = {
    mine: mine.map(said),
    onJob: onJob.map(said),
    onMachine: (job.locks ?? []).map(said),
    otherJobs: (job.locks ?? []).filter((one) => one.work_order_ref !== job.ref).map((one) => `${one.owner_name} ที่ ${one.point_id} (${one.work_order_ref})`),
    hadMine: (job.confirmations ?? []).some((one) => one.item === "locked" && one.by === account.user),
    anybodyLocked: (job.confirmations ?? []).some((one) => one.item === "locked"),
    restoreLeft: null,
  };
  const symptom = job.title ? job.title.replace(job.machine_id, "").trim() : job.reason;

  return (
    <PhoneFrame
      top={
        <>
          <Link className="back" href={back}>
            <ArrowLeft size={24} aria-hidden />
            {total > 0 ? `ขั้น ${at}` : "งาน"}
          </Link>
          <span className="anc">ส่งต่องาน</span>
          <Clock now={new Date()} timezone={round.timezone} date={false} />
        </>
      }
    >
      <LockBar locks={job.locks ?? []} you={account.user} timezone={round.timezone} />
      <Plate job={job} lamps={null} sub={<span className="w">{job.ref}</span>} />
      <p className="when" style={{ marginTop: 16 }}>
        <Th>{symptom}</Th>
        {total > 0 && <span style={{ display: "block" }}>{`อยู่ที่ขั้น ${at} จาก ${total}`}</span>}
      </p>
      <HandoverForm workOrder={job.ref} locks={locks} note={total > 0 ? `ถึงขั้นที่ ${at} จาก ${total} · ` : ""} />
    </PhoneFrame>
  );
}

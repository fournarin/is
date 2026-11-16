import { ArrowRight, BookOpen, ChevronRight, CircleAlert, CircleCheck, Info, ListOrdered, Megaphone, Printer } from "lucide-react";
import Link from "next/link";

import { NotYours, Shell } from "@/app/ui/shell";
import { Clock, PhoneFrame, Plate, Row, Th, Who } from "@/app/ui/v2/frame";
import { startWork } from "@/app/work/actions";
import { DisagreeForm } from "@/app/work/disagree-form";
import { bandFor, minutesText, seenLine } from "@/lib/display";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { currentRound, myWork, proposals, toolNames, type Ticket } from "@/lib/work";

/**
 * One job, not a menu - the way a ride-hailing app hands a driver one trip
 * (ADR-093), drawn in the design system of GATE 2 (ADR-133).
 *
 * The scheduler has already decided the order, and offering a list would let a
 * technician take the easy one first, which is what the load gate exists to
 * prevent (ADR-011, ADR-058). What is queued behind it is shown and is not
 * selectable. Every sentence on it was written by the backend (ADR-005).
 */
export default async function WorkPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; done?: string; ref?: string }>;
}) {
  const account = await requireAccount();
  const { error, done, ref } = await searchParams;
  if (account.role !== "technician") {
    return (
      <Shell account={account} current="/work">
        <NotYours home={homeFor(account.role)} what="หน้านี้เป็นหน้างานของช่าง" />
      </Shell>
    );
  }

  const [round, mine] = await Promise.all([currentRound(), myWork()]);
  const now = new Date();
  const top = (
    <>
      <Who account={account} title="งานของฉัน" />
      <Clock now={now} timezone={round.timezone} />
    </>
  );
  // What the last button did, said once (ADR-126).
  const doneLine =
    done === "closed"
      ? `ปิดงาน ${ref ?? ""} แล้ว หัวหน้ากะเห็นผลและบันทึกของคุณแล้ว`
      : done === "handed"
        ? `ส่งต่องาน ${ref ?? ""} แล้ว หัวหน้ากะจะส่งให้ช่างคนอื่น`
        : null;
  const recorded = doneLine && (
    <div className="callout is-ok v-note" role="status">
      <CircleCheck size={20} aria-hidden />
      <div>
        <Th>{doneLine}</Th>
      </div>
    </div>
  );

  if (mine.length === 0) {
    // "Nothing yet" and "waiting for your shift lead" are different sentences (ADR-005, ADR-071 §7).
    const waiting = (await proposals()).filter((one) => one.assignees.includes(account.user));
    return (
      <PhoneFrame top={top}>
        {recorded}
        <div className="v-card" style={{ marginTop: 16 }}>
          <h1 className="sym">{waiting.length > 0 ? "มีงานรอหัวหน้ากะยืนยัน" : "ยังไม่มีงานที่ส่งถึงคุณ"}</h1>
          <p style={{ marginTop: 8 }}>
            <Th>
              {waiting.length > 0
                ? `ระบบจัดงานให้คุณแล้ว ${waiting.length} งาน พอหัวหน้ากะยืนยัน งานจะขึ้นที่หน้านี้`
                : "เมื่อมีงานใหม่ จะขึ้นที่หน้านี้ทันที"}
            </Th>
          </p>
          <p className="muted" style={{ marginTop: 8 }}>
            <Th>{round.summary}</Th>
          </p>
        </div>
        <nav className="sec rows" aria-label="ทางเลือกอื่น">
          <Row icon={<Megaphone size={24} aria-hidden />} label="แจ้งซ่อมเครื่องที่เจอปัญหา" sub="เลือกสถานีและเครื่อง ไม่ต้องพิมพ์" href="/report" />
        </nav>
      </PhoneFrame>
    );
  }

  const [job, ...next] = mine as [Ticket, ...Ticket[]];
  const band = bandFor(job);
  const seen = seenLine(job, round.timezone);
  const inProgress = job.status === "in_progress";
  const hasSteps = job.steps.length > 0;
  const steps = `/work/${encodeURIComponent(job.ref)}/steps`;
  // The title is the backend's "MC-012 มอเตอร์สายพาน..."; the plate already names the machine.
  const symptom = job.title ? job.title.replace(job.machine_id, "").trim() : job.reason;
  // Amber is a machine past its threshold (solid) or forecast to be (outline) - and nothing else (ADR-133).
  const tone = job.finding_kind === "predicted" ? "band-forecast" : job.finding_kind === "detected" ? "band-over" : "";

  return (
    <PhoneFrame top={top}>
      {recorded}
      {error !== undefined && (
        <div className="callout is-bad v-note" role="alert">
          <CircleAlert size={20} aria-hidden />
          <div>
            <Th>{error}</Th>
          </div>
        </div>
      )}
      <Plate
        station={job.station}
        title={job.machine_id}
        sub={
          <>
            ใบงาน <span className="code">{job.ref}</span> · <span className="w">งานที่ 1 จาก {mine.length}</span>
          </>
        }
      />

      <section className="v-job" aria-labelledby="job-h">
        <h1 className="sym" id="job-h">
          <Th>{symptom}</Th>
        </h1>
        <div className="meta">
          <span className={`v-chip ${tone}`}>
            <Th>{band.label}</Th>
          </span>
          {inProgress && <span className="v-chip">กำลังทำ</span>}
        </div>
        {job.eta_text && (
          <p className="when">
            <Th>{job.eta_text}</Th>
          </p>
        )}
        {/* Written by the backend when the job was created, never here. */}
        <p className="v-why">
          <Th>{job.reason}</Th>
        </p>
        {seen !== null && (
          <p className="muted">
            <Th>{seen}</Th>
          </p>
        )}
      </section>

      {job.recurrence?.status === "superseded" && (
        <div className="callout is-bad v-note">
          <CircleAlert size={20} aria-hidden />
          <div>
            <b>สถานะล่าสุด:</b> อาการนี้เกินเกณฑ์แล้ว ไม่ใช่แค่คาดการณ์ ให้ถือเป็นงานด่วน
          </div>
        </div>
      )}
      {job.handover_note && (
        <div className="callout is-lock v-note">
          <Info size={20} aria-hidden />
          <div>
            <b>ช่างคนก่อนทำไว้ถึงตรงนี้:</b> <Th>{job.handover_note}</Th>
          </div>
        </div>
      )}
      {job.playbook_warning !== null && (
        <div className="callout is-bad v-note">
          <CircleAlert size={20} aria-hidden />
          <div>
            <b>คู่มือของเครื่องนี้เพิ่งถูกเปลี่ยน</b> · ขั้นตอนชุดนี้รอวิศวกรตรวจใหม่ ให้เทียบกับคู่มือก่อนลงมือ
          </div>
        </div>
      )}

      <div className="go">
        {inProgress ? (
          <Link className="btn pri" href={steps}>
            ทำต่อ
            <ArrowRight size={24} aria-hidden />
          </Link>
        ) : (
          <form action={startWork.bind(null, job.ref)}>
            <button type="submit" className="btn pri">
              รับงานและเริ่มทำ
              <ArrowRight size={24} aria-hidden />
            </button>
          </form>
        )}
      </div>
      {next.length > 0 && (
        <a className="nxt" href="#queue">
          <span className="t">
            <b>ถัดไป {next.length} งาน</b> · <span className="code">{next[0]!.machine_id}</span>
          </span>
          <ChevronRight size={24} aria-hidden />
        </a>
      )}

      <section className="sec" aria-labelledby="why-h">
        <h2 id="why-h">ทำไมต้องทำงานนี้ก่อน</h2>
        <p className="v-card">
          {job.priority_reason === "" ? <span className="muted">ยังไม่ได้จัดลำดับ</span> : <Th>{job.priority_reason}</Th>}
        </p>
        <DisagreeForm workOrder={job.ref} timezone={round.timezone} />
      </section>

      <section className="sec" aria-labelledby="prep-h">
        <h2 id="prep-h">เตรียมก่อนเดินไปเครื่อง</h2>
        <dl className="v-facts">
          <div>
            <dt>เวลา</dt>
            <dd>
              {minutesText(job.estimated_minutes)}
              {job.estimate_is_fallback && " · ค่าประมาณคร่าว ๆ"}
            </dd>
          </div>
          <div>
            <dt>ทักษะ</dt>
            <dd>
              <Th>{job.required_skill_name ?? "ทั่วไป"}</Th> · {job.required_technicians} คน
            </dd>
          </div>
          {job.tools.length > 0 && (
            <div>
              <dt>เครื่องมือ</dt>
              <dd>
                <Th>{toolNames(job).join(" · ")}</Th>
              </dd>
            </div>
          )}
          <div>
            <dt>ขั้นตอน</dt>
            <dd>{hasSteps ? `${job.steps.length} ขั้น` : "ยังไม่มีขั้นตอนที่อนุมัติ · ดูคู่มือ"}</dd>
          </div>
        </dl>
      </section>

      <nav className="sec rows" aria-label="ทางเลือกอื่น">
        {inProgress && (
          <Row
            icon={hasSteps ? <ListOrdered size={24} aria-hidden /> : <BookOpen size={24} aria-hidden />}
            label={hasSteps ? "ดูทุกขั้น" : "ดูว่าคู่มือหน้าไหน"}
            sub={hasSteps ? `${job.steps.length} ขั้น` : "ยังไม่มีขั้นตอนที่อนุมัติ"}
            href={steps}
          />
        )}
        <Row icon={<Printer size={24} aria-hidden />} label="พิมพ์ใบงาน" sub="A4 หน้าเดียว ขาวดำได้" href={`/work/${encodeURIComponent(job.ref)}/print`} />
        <Row icon={<Megaphone size={24} aria-hidden />} label="แจ้งซ่อมเครื่องอื่น" sub="เครื่องที่เจอปัญหาระหว่างทาง" href="/report" />
      </nav>

      {next.length > 0 && (
        <section className="sec" id="queue" aria-labelledby="queue-h">
          {/* Shown and not selectable: nothing in this list is a link (ADR-011). */}
          <h2 id="queue-h">งานถัดไปของคุณ ({next.length})</h2>
          <ul className="queue">
            {next.map((one) => (
              <li key={one.ref}>
                <b className="code">{one.machine_id}</b> · <Th>{bandFor(one).label}</Th>
                <span className="muted">
                  <Th>{one.reason}</Th>
                </span>
              </li>
            ))}
          </ul>
          <p className="muted" style={{ marginTop: 8 }}>
            ระบบเรียงลำดับไว้แล้ว ปิดงานนี้แล้วงานถัดไปจะขึ้นมาเอง
          </p>
        </section>
      )}
    </PhoneFrame>
  );
}

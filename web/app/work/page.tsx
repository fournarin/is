import { ArrowRight, BookOpen, ChevronRight, CircleAlert, CircleCheck, Info, ListOrdered, Megaphone, Printer } from "lucide-react";
import Link from "next/link";

import { KeepFresh } from "@/app/ui/keep-fresh";
import { NotYours, Shell } from "@/app/ui/shell";
import { Approved, Clock, PhoneFrame, Plate, Prio, Row, Th, Who, signalsAreSynthetic } from "@/app/ui/v2/frame";
import { startWork } from "@/app/work/actions";
import { DisagreeForm } from "@/app/work/disagree-form";
import { OUTCOME, UNIT, bandFor, figure, minutesText, plantDay, plantTime, seenLine } from "@/lib/display";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { currentRound, lineLamps, myWork, proposals, toolNames, type Reading, type Ticket } from "@/lib/work";

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

  const [round, mine, lamps] = await Promise.all([currentRound(), myWork(), lineLamps()]);
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
  const total = job.steps.length;
  // Where the steps have got to: the last mark, or the first step (ADR-134).
  const at = Math.min(Math.max(job.step_reached ?? 1, 1), Math.max(total, 1));
  const steps = `/work/${encodeURIComponent(job.ref)}/steps`;
  // The title is the backend's "MC-012 มอเตอร์สายพาน..."; the plate already names the machine.
  const symptom = job.title ? job.title.replace(job.machine_id, "").trim() : job.reason;
  const tools = toolNames(job);
  const history = job.history ?? [];

  return (
    <PhoneFrame top={top}>
      <KeepFresh />
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
        job={job}
        lamps={lamps}
        sub={
          <>
            {job.machine_model && `${job.machine_model} · `}
            <span className="w">{job.ref}</span>
            {mine.length > 1 && (
              <>
                {" · "}
                <span className="w">{`งานที่ 1 จาก ${mine.length}`}</span>
              </>
            )}
          </>
        }
      />

      <section className="v-job" aria-labelledby="job-h">
        <h1 className="sym" id="job-h">
          <Th>{symptom}</Th>
        </h1>
        <div className="meta">
          <Prio severity={job.severity} />
          {/* With a reading, the band sits beside it as a swatch; without one, here, in plain words. */}
          {!job.reading && (
            <span className="v-chip">
              <Th>{band.label}</Th>
            </span>
          )}
          {inProgress && <span className="v-chip">กำลังทำ</span>}
          {inProgress && total > 0 && (
            <span className="prog1">
              <b>{`ขั้น ${at}/${total}`}</b>
              {job.started_at && ` · เริ่ม ${plantTime(job.started_at, round.timezone)}`}
            </span>
          )}
        </div>
        {job.eta_text && (
          <p className="when">
            <Th>{job.eta_text}</Th>
          </p>
        )}
        {/* Written by the backend when the job was created, never here; the
            "<symptom> ที่เครื่อง <machine> · " it opens with is the heading above. */}
        <p className="v-why">
          <Th>{withoutHeading(job.reason, symptom)}</Th>
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
          <Link className="btn pri" href={total > 0 ? `${steps}?step=${at}` : steps}>
            {total > 0 ? `ทำต่อขั้น ${at}` : "ดูว่าคู่มือหน้าไหน"}
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
            <b>{`ถัดไป ${next.length} งาน`}</b> · <span className="code">{next[0]!.machine_id}</span>
          </span>
          <Prio severity={next[0]!.severity} />
          <ChevronRight size={24} aria-hidden />
        </a>
      )}
      <p className="upd">{`อัปเดต ${new Intl.DateTimeFormat("th-TH", { timeZone: round.timezone, timeStyle: "medium" }).format(now)} · หน้านี้อัปเดตเอง`}</p>

      {job.reading && <ReadingBox reading={job.reading} band={band.label} detected={job.finding_kind === "detected"} />}

      <section className="sec" aria-labelledby="hist-h">
        <h2 id="hist-h">
          {`ครั้งก่อนที่เครื่องนี้${signalsAreSynthetic() && history.length > 0 ? " · จำลอง" : ""}`}
        </h2>
        {history.length > 0 ? (
          <ol className="hist">
            {history.map((past) => (
              <li key={past.ref}>
                <p className="h1">
                  {past.page !== null && <span className="m w">{`คู่มือหน้า ${past.page}`}</span>}
                  <span className="v-chip">{OUTCOME[past.outcome] ?? past.outcome}</span>{" "}
                  <b className="w">{plantDay(past.closed_at, round.timezone)}</b>
                  <span className="w">{` · ${minutesText(past.minutes)}${past.by.length > 0 ? ` · ${past.by.join(", ")}` : ""}`}</span>
                </p>
                {past.note && (
                  <p>
                    <q>
                      <Th>{past.note}</Th>
                    </q>
                  </p>
                )}
              </li>
            ))}
          </ol>
        ) : (
          <p className="v-card">ยังไม่มีงานที่ปิดแล้วบนเครื่องนี้</p>
        )}
      </section>

      <section className="sec" aria-labelledby="prep-h">
        <h2 id="prep-h">เตรียมก่อนเดินไปเครื่อง</h2>
        <dl className="v-facts">
          {tools.length > 0 && (
            <div>
              <dt>เครื่องมือ</dt>
              <dd>
                <ul>
                  {tools.map((tool) => (
                    <li key={tool}>
                      <Th>{tool}</Th>
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          )}
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
        </dl>
      </section>

      <nav className="sec rows" aria-label="ทางเลือกอื่น">
        <Row
          icon={total > 0 ? <ListOrdered size={24} aria-hidden /> : <BookOpen size={24} aria-hidden />}
          label={total > 0 ? "ดูทุกขั้น" : "ดูว่าคู่มือหน้าไหน"}
          sub={total > 0 ? `${total} ขั้น${job.step_reached ? ` · ถึงขั้น ${at} แล้ว` : ""}` : "ยังไม่มีขั้นตอนที่อนุมัติ"}
          href={steps}
        />
        <DisagreeForm
          workOrder={job.ref}
          timezone={round.timezone}
          priorityReason={job.priority_reason === "" ? "ยังไม่ได้จัดลำดับ" : <Th>{job.priority_reason}</Th>}
        />
        <Row icon={<Megaphone size={24} aria-hidden />} label="แจ้งซ่อมเครื่องอื่น" sub="เครื่องที่เจอปัญหาระหว่างทาง" href="/report" />
        <Row icon={<Printer size={24} aria-hidden />} label="พิมพ์ใบงาน" sub="A4 หน้าเดียว ขาวดำได้" href={`/work/${encodeURIComponent(job.ref)}/print`} />
      </nav>

      {next.length > 0 && (
        <section className="sec" id="queue" aria-labelledby="queue-h">
          {/* Shown and not selectable: nothing in this list is a link (ADR-011). */}
          <h2 id="queue-h">{`ถัดไป ${next.length} งาน · ตามลำดับที่ระบบจัด`}</h2>
          {next.map((one) => (
            <div className="qrow" key={one.ref}>
              <span className="t">
                <Th>{one.title ? one.title.replace(one.machine_id, "").trim() : one.reason}</Th>
                <small>
                  <span className="code">{one.machine_id}</span> · {one.ref} · <Th>{bandFor(one).label}</Th>
                </small>
              </span>
              <Prio severity={one.severity} />
            </div>
          ))}
          <p className="muted" style={{ marginTop: 8 }}>
            ระบบเรียงลำดับไว้แล้ว ปิดงานนี้แล้วงานถัดไปจะขึ้นมาเอง
          </p>
        </section>
      )}

      {job.approval && <Approved approval={job.approval} timezone={round.timezone} />}
    </PhoneFrame>
  );
}

/**
 * The reading behind the ticket, as its Finding recorded it (ADR-134). A box the
 * Finding did not carry is left out rather than filled with a figure.
 */
function ReadingBox({ reading, band, detected }: { reading: Reading; band: string; detected: boolean }) {
  const unit = reading.unit ? (UNIT[reading.unit] ?? reading.unit) : "";
  const boxes: { label: string; value: number; unit: string }[] = [];
  if (reading.value !== null) boxes.push({ label: "ตอนนี้", value: reading.value, unit });
  if (reading.threshold !== null) boxes.push({ label: "เกณฑ์", value: reading.threshold, unit });
  if (reading.slope_per_hour !== null) {
    boxes.push({
      label: reading.slope_per_hour >= 0 ? "เพิ่มขึ้น" : "ลดลง",
      value: Math.abs(reading.slope_per_hour),
      unit: `${unit}/ชม.`,
    });
  }
  return (
    <section className="sec" aria-labelledby="sig-h">
      <h2 id="sig-h">
        <span>
          <Th>{reading.metric_title ?? reading.metric_name}</Th>
        </span>
        <span className={`r sw${detected ? " ov" : ""}`}>
          <i aria-hidden />
          <span>
            <Th>{band}</Th>
          </span>
        </span>
      </h2>
      {boxes.length > 0 && (
        <dl className="stats">
          {boxes.map((box) => (
            <div key={box.label}>
              <dt>{box.label}</dt>
              <dd>
                {figure(box.value)}
                <small>{box.unit}</small>
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

/** The backend's reason without the "<symptom> ที่เครื่อง <machine> · " the heading already says. */
function withoutHeading(reason: string, symptom: string): string {
  const cut = reason.indexOf(" · ");
  return cut > 0 && reason.startsWith(symptom) ? reason.slice(cut + 3) : reason;
}

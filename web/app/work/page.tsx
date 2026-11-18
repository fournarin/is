import { ArrowRight, BookOpen, ChevronRight, CircleAlert, CircleCheck, History, Info, ListOrdered, Megaphone, Printer } from "lucide-react";
import Link from "next/link";

import { KeepFresh } from "@/app/ui/keep-fresh";
import { SheetClose } from "@/app/ui/v2/sheet-close";
import { NotYours, Shell } from "@/app/ui/shell";
import { Approved, Clock, PhoneFrame, Plate, Prio, Row, Th, Who, signalsAreSynthetic } from "@/app/ui/v2/frame";
import { startWork } from "@/app/work/actions";
import { DisagreeForm } from "@/app/work/disagree-form";
import { OUTCOME, UNIT, bandFor, figure, minutesText, plantDateTime, plantDay, seenLine } from "@/lib/display";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { currentRound, lineLamps, myLocks, myWork, proposals, toolNames, type Reading, type Ticket } from "@/lib/work";
import { MyLocks } from "@/app/work/my-locks";

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

  const [round, mine, lamps, locksOn] = await Promise.all([currentRound(), myWork(), lineLamps(), myLocks()]);
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
        : done === "unlocked"
          ? "บันทึกว่าปลดกุญแจแล้ว ทะเบียนอัปเดตแล้ว"
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
        <MyLocks locks={locksOn} timezone={round.timezone} />
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
        // Trimmed (Q14): the machine, and how many jobs there are; model and order number are lower down.
        sub={mine.length > 1 ? <span className="w">{`งานที่ 1 จาก ${mine.length}`}</span> : null}
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
          {/* "◆ สูง · ขั้น 2/9" (round 3 item 2): the step says it is under way; when it started is on the steps. */}
          {inProgress && total > 0 && (
            <span className="prog1">
              <span aria-hidden>{"· "}</span>
              <b>{`ขั้น ${at}/${total}`}</b>
            </span>
          )}
        </div>
        {/* One line above the fold, the interval always with the time (ADR-123), and only here
            (round 3 item 2): the reading below no longer repeats it. */}
        {job.eta && job.eta_confidence_minutes !== null && (
          <p className="when">{`ถึงเกณฑ์ราว ${plantDateTime(job.eta, round.timezone)} น. · ±${withinText(job.eta_confidence_minutes)}`}</p>
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

      {/* What the reporter saw, before the walk to the machine (trial-kong, ADR-142). */}
      {job.photo && (
        <a className="mref v-note" href={`/work/${encodeURIComponent(job.ref)}/photo`}>
          {/* eslint-disable-next-line @next/next/no-img-element -- served through this origin from the API; nothing to optimise */}
          <img className="thumb" src={`/work/${encodeURIComponent(job.ref)}/photo`} alt="" />
          <span className="t">
            รูปจากคนแจ้ง
            <small>แตะเพื่อดูเต็มจอ</small>
          </span>
        </a>
      )}
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
      {job.reading && (
        <ReadingBox reading={job.reading} band={band.label} detected={job.finding_kind === "detected"} forecast={job.eta ? null : job.eta_text} />
      )}

      <section className="sec" aria-labelledby="hist-h">
        <h2 id="hist-h">
          {`ครั้งก่อนที่เครื่องนี้${signalsAreSynthetic() && history.length > 0 ? " · จำลอง" : ""}`}
        </h2>
        {history.length > 0 ? (
          // Two lines a job; what the last person wrote opens in a sheet (Q13, ADR-139).
          <div className="rows">
            {history.map((past) => (
              <details className="sheet" key={past.ref}>
                <summary>
                  <History size={24} aria-hidden />
                  <span className="t">
                    <span className="w">{`${OUTCOME[past.outcome] ?? past.outcome} · ${plantDay(past.closed_at, round.timezone)}`}</span>
                    <small>{`${minutesText(past.minutes)}${past.by.length > 0 ? ` · ${past.by.join(", ")}` : ""}${past.note ? " · มีบันทึก" : ""}`}</small>
                  </span>
                  <ChevronRight size={24} aria-hidden />
                </summary>
                <div className="panel">
                  <div className="grab">
                    <b>{`ครั้งก่อน · ${plantDay(past.closed_at, round.timezone)}`}</b>
                    <SheetClose />
                  </div>
                  <dl className="v-facts" style={{ padding: 0 }}>
                    <div>
                      <dt>ผล</dt>
                      <dd>{OUTCOME[past.outcome] ?? past.outcome}</dd>
                    </div>
                    <div>
                      <dt>ใช้เวลา</dt>
                      <dd>{minutesText(past.minutes)}</dd>
                    </div>
                    {past.by.length > 0 && (
                      <div>
                        <dt>ช่าง</dt>
                        <dd>{past.by.join(", ")}</dd>
                      </div>
                    )}
                    {past.page !== null && (
                      <div>
                        <dt>คู่มือ</dt>
                        <dd>{`หน้า ${past.page}`}</dd>
                      </div>
                    )}
                    <div>
                      <dt>ใบงาน</dt>
                      <dd className="code">{past.ref}</dd>
                    </div>
                  </dl>
                  {past.note && (
                    <p style={{ marginTop: 12 }}>
                      <q>
                        <Th>{past.note}</Th>
                      </q>
                    </p>
                  )}
                </div>
              </details>
            ))}
          </div>
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

      <MyLocks locks={locksOn.filter((one) => one.work_order_ref !== job.ref)} timezone={round.timezone} />
      {job.approval && <Approved approval={job.approval} timezone={round.timezone} />}
      <p className="upd">{`${job.machine_model ? `${job.machine_model} · ` : ""}${job.ref} · อัปเดต ${new Intl.DateTimeFormat("th-TH", { timeZone: round.timezone, timeStyle: "medium" }).format(now)} · หน้านี้อัปเดตเอง`}</p>
    </PhoneFrame>
  );
}

/**
 * The reading behind the ticket, as its Finding recorded it (ADR-134). A box the
 * Finding did not carry is left out rather than filled with a figure.
 */
function ReadingBox({
  reading,
  band,
  detected,
  forecast,
}: {
  reading: Reading;
  band: string;
  detected: boolean;
  forecast: string | null;
}) {
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
      {forecast && (
        <p className="muted" style={{ marginBottom: 8 }}>
          <Th>{forecast}</Th>
        </p>
      )}
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

/** "2 ชม." / "45 นาที" for the give-or-take beside a forecast time. */
function withinText(minutes: number): string {
  return minutes >= 120 ? `${Math.round(minutes / 60)} ชม.` : `${minutes} นาที`;
}

import { ArrowDown, ArrowLeft, ArrowRightLeft, BookOpen, Lock, Check, ChevronRight, CircleAlert, History, Image as Figure, Info, ListOrdered, Phone, SquareCheck } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { NotThere, Shell } from "@/app/ui/shell";
import { Approved, Clock, PhoneFrame, Plate, Row, Th, signalsAreSynthetic, stationNumber } from "@/app/ui/v2/frame";
import { moveTo } from "@/app/work/actions";
import { KindHeader, NotYet, OfflineNote, Points, WaitBox, needed, neededLine, whoFor } from "@/app/work/[ref]/steps/energy";
import { LockBar } from "@/app/ui/v2/signs";
import { SheetClose } from "@/app/ui/v2/sheet-close";
import { firstUnfinished, nextLine, waitEnds } from "@/lib/energy";
import { plantTime } from "@/lib/display";
import { pagesNamed } from "@/lib/page-references";
import { evidence } from "@/lib/review";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { currentRound, lineLamps, ticketAt, type Lamp, type Ticket } from "@/lib/work";

/**
 * One step at a time, because the other hand is holding a tool - with every step
 * one tap away on the rail, so nobody loses their place (ADR-093, ADR-133).
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
  searchParams: Promise<{ step?: string; error?: string }>;
}) {
  const account = await requireAccount();
  const { ref } = await params;
  const { step, error } = await searchParams;

  const [job, round, lamps] = await Promise.all([ticketAt(decodeURIComponent(ref)), currentRound(), lineLamps()]);
  if (job === null) {
    return (
      <Shell account={account} current="/work">
        <NotThere home={homeFor(account.role)} what="ไม่พบใบงานนี้" />
      </Shell>
    );
  }
  const total = job.steps.length;
  const close = `/work/${encodeURIComponent(job.ref)}/close`;
  const manualPage = (doc: string, page: number, fromStep?: number) =>
    `/work/${encodeURIComponent(job.ref)}/manual?doc=${encodeURIComponent(doc)}&page=${page}` +
    (fromStep === undefined ? "" : `&step=${fromStep}`);
  const number = stationNumber(job);
  // The station stays in sight on every step: its number, its name, the machine (design system).
  const top = (
    <>
      <Link className="back" href="/work">
        <ArrowLeft size={24} aria-hidden />
        งาน
      </Link>
      {number !== null && (
        <span className="stile" role="img" aria-label={job.station ?? undefined}>
          {number}
        </span>
      )}
      <span className="anc">
        <Th>{job.station_name ?? job.machine_id}</Th>
        <small className="w">{job.station_name ? job.machine_id : `ใบงาน ${job.ref}`}</small>
      </span>
      <Clock now={new Date()} timezone={round.timezone} date={false} />
    </>
  );
  const history = job.history ?? [];
  const handover = job.handover_note && (
    <div className="callout is-lock v-note">
      <Info size={20} aria-hidden />
      <div>
        <b>ช่างคนก่อนทำไว้ถึงตรงนี้:</b> <Th>{job.handover_note}</Th>
      </div>
    </div>
  );

  if (total === 0) {
    // The plate below names the station, so the bar keeps only the way back and the time.
    const bare = (
      <>
        <Link className="back" href="/work">
          <ArrowLeft size={24} aria-hidden />
          งาน
        </Link>
        <span style={{ flex: 1 }} />
        <Clock now={new Date()} timezone={round.timezone} date={false} />
      </>
    );
    return (
      <PhoneFrame top={bare}>
        <NoSteps job={job} manualPage={manualPage} lamps={lamps} close={close} handover={handover} timezone={round.timezone} />
      </PhoneFrame>
    );
  }

  // 1-based, matching what the screen says. Anything outside the playbook is a
  // typed URL rather than a link this app produced.
  // No step in the link: resume where the job got to (ADR-134).
  const at = step === undefined ? Math.min(job.step_reached ?? 1, total) : Number(step);
  if (!Number.isInteger(at) || at < 1 || at > total) {
    notFound();
  }
  const current = job.steps[at - 1]!;
  const last = at === total;

  // Other pages the step sends the technician to - "the lockout procedure on
  // page 2" - checked against what the index read of the same manual. A page it
  // never saw is said to be missing rather than offered as a link to nothing.
  const named = await Promise.all(
    pagesNamed(`${current.text} ${current.text_th ?? ""}`, current.page).map(async (page) => {
      const read = await evidence(current.source_doc, page).catch(() => undefined);
      return { page, missing: read === null || read?.outcome === "not_indexed" };
    }),
  );

  const now = new Date();
  // This step's own confirmations, or an earlier step's left unfinished: the API refuses either.
  const earlier = firstUnfinished(job.steps, job.confirmations ?? [], at, now, whoFor(job, account.user));
  const missing = needed(job, at, now, account.user);
  const waitUntil = current.wait_minutes ? waitEnds(current, at, job.confirmations ?? []) : null;

  return (
    <PhoneFrame top={top}>
      <LockBar locks={job.locks ?? []} you={account.user} timezone={round.timezone} />
      {(current.kind ?? "normal") !== "normal" && <OfflineNote />}
      {error !== undefined && error !== "" && (
        <div className="callout is-bad v-note" role="alert">
          <CircleAlert size={20} aria-hidden />
          <div>
            <Th>{error}</Th>
          </div>
        </div>
      )}
      {/* REQ-H-05: isolating without verifying zero energy is not a procedure to work from. */}
      {job.missing_verify && (
        <div className="callout is-bad v-note" role="alert">
          <CircleAlert size={20} aria-hidden />
          <div>
            <b>ขาดการตรวจยืนยันพลังงานเป็นศูนย์</b> · แจ้งหัวหน้ากะก่อนเริ่ม
          </div>
        </div>
      )}
      {handover}
      {job.playbook_warning !== null && (
        <div className="callout is-bad v-note">
          <CircleAlert size={20} aria-hidden />
          <div>
            <b>คู่มือเพิ่งถูกเปลี่ยน</b> · ขั้นตอนชุดนี้รอวิศวกรตรวจใหม่ ให้เทียบกับคู่มือก่อน
          </div>
        </div>
      )}

      <div className="v-progress">
        <span className="v-big" role="heading" aria-level={1} aria-label={`ขั้นที่ ${at} จาก ${total}`}>
          <b aria-hidden>{at}</b>
          <small aria-hidden>/{total}</small>
        </span>
        <span className="rail" aria-hidden>
          {job.steps.map((_, index) => {
            const n = index + 1;
            return (
              // A slim segment a step (Q14): where you are, without nine numbered boxes.
              <span key={n} className={n < at ? "is-done" : n === at ? "cur" : undefined} />
            );
          })}
        </span>
      </div>

      <section className="v-card step" aria-label={`ขั้นที่ ${at}`}>
        <KindHeader step={current} revision={job.approval?.revision ?? null} />
        <p className="th">
          <Th>{current.text_th ?? current.text}</Th>
        </p>
        {/* The cited page inside the job, one tap back to this step (third trial). */}
        <Link className="mref" href={manualPage(current.source_doc, current.page, at)}>
          <span className="thumb">
            <Figure size={28} aria-hidden />
          </span>
          <span className="t">
            {`คู่มือหน้า ${current.page}`}
            <small>{`${job.machine_model ? `${job.machine_model} · ` : ""}อ่านทั้งหน้า`}</small>
          </span>
          <ChevronRight size={24} aria-hidden />
        </Link>
        {named.map(({ page, missing }) =>
          missing ? (
            <div className="callout is-bad v-note" key={page} style={{ background: "var(--canvas)" }}>
              <CircleAlert size={20} aria-hidden />
              <div>
                <Th>{`หน้า ${page} ที่ขั้นนี้อ้างถึง ไม่มีในคู่มือที่ระบบอ่านไว้ — ถามวิศวกรก่อนทำขั้นนี้`}</Th>
              </div>
            </div>
          ) : (
            <Link className="mref" key={page} href={manualPage(current.source_doc, page, at)}>
              <span className="thumb">
                <BookOpen size={28} aria-hidden />
              </span>
              <span className="t">
                <Th>{`อ่านหน้า ${page} ที่ขั้นนี้อ้างถึง`}</Th>
              </span>
              <ChevronRight size={24} aria-hidden />
            </Link>
          ),
        )}
        {/* The manual's own words stay under the Thai: the citation proves those (ADR-095). */}
        {current.text_th !== null && (
          <p className="en" lang="en">
            <span className="lbl" lang="th">
              <Th>{`ต้นฉบับ หน้า ${current.page}${signalsAreSynthetic() ? " · จำลอง" : ""}`}</Th>
            </span>
            {current.text}
          </p>
        )}
      </section>

      {/* An energy step's next action is a point below the manual's words: on a small phone it starts
          under the fold, so a link to it waits at the bottom of the first screen and settles in place
          above the points once they are reached (round 3 item 4). */}
      {earlier === null && (current.isolation_points ?? []).length > 0 && missing.some((one) => one.item !== "wait_started") && (
        <div className="jump sticky">
          <a className="btn pri" href="#pts">
            <ArrowDown size={24} aria-hidden />
            <span>
              <Th>{nextLine(missing)}</Th>
            </span>
          </a>
        </div>
      )}
      <Points job={job} number={at} you={account.user} now={now} />
      <WaitBox job={job} number={at} now={now} timezone={round.timezone} />

      <div className="done-btn">
        {earlier !== null && missing.length === 0 ? (
          <>
            <div className="btn off" aria-disabled>
              <Lock size={24} aria-hidden />
              ทำขั้นนี้แล้ว ถัดไป
            </div>
            <p className="miss">
              {`ขั้นที่ ${earlier.number} ยังยืนยันไม่ครบ · ${neededLine(earlier.missing).replace("ยังต้องยืนยัน: ", "")}`}
            </p>
          </>
        ) : missing.length > 0 ? (
          // Refused by the API as well; this only says so before the tap (ADR-135).
          <NotYet
            missing={missing}
            label={last ? "ทำขั้นนี้แล้ว ไปปิดงาน" : "ทำขั้นนี้แล้ว ถัดไป"}
            until={waitUntil && missing.every((one) => one.item === "wait_started") ? `ถัดไปได้เมื่อ ${plantTime(waitUntil.toISOString(), round.timezone)}` : null}
          />
        ) : last ? (
          <Link className="btn pri" href={`${close}?reached=${total}`}>
            <SquareCheck size={24} aria-hidden />
            ครบทุกขั้น ปิดงาน
          </Link>
        ) : (
          // A form, so moving on is kept and the job page resumes here (ADR-134).
          <form action={moveTo.bind(null, job.ref, at + 1)}>
            <button type="submit" className="btn pri">
              <Check size={24} aria-hidden />
              ทำขั้นนี้แล้ว ถัดไป
            </button>
          </form>
        )}
      </div>

      <nav className="after rows" aria-label="ทางเลือกอื่น">
        <details className="sheet">
          <summary>
            <ListOrdered size={24} aria-hidden />
            <span className="t">
              ดูทุกขั้น
              <small>{`ทั้ง ${total} ขั้น · อยู่ที่ขั้น ${at}`}</small>
            </span>
          </summary>
          <div className="panel">
          <div className="grab">
            <b>{`ทุกขั้น (${total})`}</b>
            <SheetClose />
          </div>
        <ol className="allsteps">
          {job.steps.map((one, index) => {
            const n = index + 1;
            return (
              <li key={n} className={n < at ? "is-done" : n === at ? "cur" : undefined}>
                <Link href={`?step=${n}`} aria-current={n === at ? "step" : undefined}>
                  <span className="n">{n < at ? <Check size={16} strokeWidth={3} aria-hidden /> : n}</span>
                  <span>
                    <Th>{one.text_th ?? one.text}</Th>
                    <small className="muted" style={{ display: "block" }}>
                      คู่มือหน้า {one.page}
                    </small>
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
          </div>
        </details>
        {history.length > 0 && (
          <Row
            icon={<History size={24} aria-hidden />}
            label="ครั้งก่อนที่เครื่องนี้"
            sub={`${history.length} ครั้ง${signalsAreSynthetic() ? " · จำลอง" : ""}`}
            href="/work#hist-h"
          />
        )}
        <Row
          icon={<ArrowRightLeft size={24} aria-hidden />}
          label="ส่งต่องาน"
          sub={`ให้คนอื่นทำต่อ บันทึกว่าถึงขั้น ${at} จาก ${total}`}
          href={`/work/${encodeURIComponent(job.ref)}/handover?reached=${at}`}
        />
        <Row
          icon={<SquareCheck size={24} aria-hidden />}
          label="ปิดงาน"
          sub="ตอบผลและนาทีที่ต้องรอ"
          href={`${close}?reached=${last && missing.length === 0 ? total : at - 1}`}
        />
      </nav>
      {job.approval && <Approved approval={job.approval} timezone={round.timezone} />}
    </PhoneFrame>
  );
}

/**
 * A job with no approved steps (REQ-H-08, principle 5): saying so beats inventing
 * a procedure. The engineer to ask is named, the manual pages that might help are
 * offered as pages to read, and handing over and closing work as on any job.
 */
function NoSteps({
  job,
  manualPage,
  lamps,
  close,
  handover,
  timezone,
}: {
  job: Ticket;
  manualPage: (doc: string, page: number) => string;
  lamps: Lamp[][] | null;
  close: string;
  handover: ReactNode;
  timezone: string;
}) {
  const where = job.where_to_look ?? [];
  const engineer = job.engineer ? `วิศวกร (${job.engineer})` : "วิศวกร";
  return (
    <>
      <Plate job={job} lamps={lamps} sub={<span className="w">{job.ref}</span>} />
      <p className="when" style={{ marginTop: 12 }}>
        <Th>{job.title ? job.title.replace(job.machine_id, "").trim() : job.reason}</Th>
      </p>
      <div className="callout is-lock v-note" role="note">
        <CircleAlert size={20} aria-hidden />
        <div>
          {/* Short enough that the actions under it start above the fold at 360x640 (set 2 review S6). */}
          <h1 className="nop">ไม่มีขั้นตอนที่อนุมัติ</h1>
          <p>
            <b>อย่าเดาขั้นตอน</b> · <Th>{`ดูคู่มือ หรือโทรถาม${engineer}`}</Th>
          </p>
        </div>
      </div>
      {handover}
      {/* Right under the callout, so the first action is on the first screen at 360x640 (S9). */}
      <nav className="rows v-note" aria-label="ทางเลือก">
        {/* No number is kept for anybody yet, so this says who to ask and does not pretend to dial. */}
        <div className="rw info">
          <Phone size={24} aria-hidden />
          <span className="t">
            {`โทรถาม${engineer}`}
            <small>เบอร์ยังไม่ได้ตั้งค่าในระบบ · ถามหัวหน้ากะ</small>
          </span>
        </div>
        <Row icon={<ArrowRightLeft size={24} aria-hidden />} label="ส่งต่องาน" sub="ให้คนที่มีทักษะทำต่อ" href={`/work/${encodeURIComponent(job.ref)}/handover`} />
        <Row icon={<SquareCheck size={24} aria-hidden />} label="ปิดงาน" sub="ตอบผลและนาทีที่ต้องรอ" href={close} />
      </nav>
      {where.length > 0 && (
        <nav className="sec rows" aria-label="หน้าคู่มือที่อาจช่วย">
          {where.map((one) =>
            one.page ? (
              <Row
                key={`${one.document_id}#${one.page}`}
                icon={<BookOpen size={24} aria-hidden />}
                label={`${one.manual} หน้า ${one.page}`}
                // ADR-118: a draft's page is a page to read, never a step.
                sub={one.from_unapproved_draft ? "หน้าที่ร่างขั้นตอนอ้างถึง ยังไม่ผ่านการอนุมัติของวิศวกร" : "อ่านในใบงานนี้"}
                href={manualPage(one.document_id, one.page)}
              />
            ) : (
              <a className="rw" key={one.document_id} href={`/manual/${encodeURIComponent(one.document_id)}`} target="_blank" rel="noreferrer">
                <BookOpen size={24} aria-hidden />
                <span className="t">
                  {one.manual}
                  <small>เปิดไฟล์คู่มือ (แท็บใหม่)</small>
                </span>
              </a>
            ),
          )}
        </nav>
      )}
      {/* Finding 11: a PM task records no page, so the screen says where in the manual to look. */}
      {job.where_to_look_note && (
        <div className="callout v-note">
          <Info size={20} aria-hidden />
          <div>
            <Th>{job.where_to_look_note}</Th>
          </div>
        </div>
      )}
      <p className="prov">
        <Th>ระบบไม่สร้างขั้นตอนให้ระหว่างทำงาน · ปิดงานและส่งต่อได้ตามปกติ</Th>
        {" · "}
        <Th>{job.reason}</Th>
        {job.started_at && ` · เริ่ม ${plantTime(job.started_at, timezone)} น.`}
        {job.eta_text && (
          <>
            {" · "}
            <Th>{job.eta_text}</Th>
          </>
        )}
      </p>
    </>
  );
}

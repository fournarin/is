import { ArrowLeft, ArrowRight, BookOpen, Check, CircleAlert, ChevronRight, Info, ListOrdered, SquareCheck } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { NotThere, Shell } from "@/app/ui/shell";
import { Clock, PhoneFrame, Plate, Row, Th } from "@/app/ui/v2/frame";
import { HandoverForm } from "@/app/work/[ref]/steps/handover-form";
import { pagesNamed } from "@/lib/page-references";
import { evidence } from "@/lib/review";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { currentRound, ticketAt, type Ticket } from "@/lib/work";

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
  searchParams: Promise<{ step?: string }>;
}) {
  const account = await requireAccount();
  const { ref } = await params;
  const { step } = await searchParams;

  const [job, round] = await Promise.all([ticketAt(decodeURIComponent(ref)), currentRound()]);
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
  const top = (
    <>
      <Link className="back" href="/work">
        <ArrowLeft size={24} aria-hidden />
        งาน
      </Link>
      <span className="anc">
        <span className="code">{job.machine_id}</span>
        <small>ใบงาน {job.ref}</small>
      </span>
      <Clock now={new Date()} timezone={round.timezone} date={false} />
    </>
  );
  const handover = job.handover_note && (
    <div className="callout is-lock v-note">
      <Info size={20} aria-hidden />
      <div>
        <b>ช่างคนก่อนทำไว้ถึงตรงนี้:</b> <Th>{job.handover_note}</Th>
      </div>
    </div>
  );

  if (total === 0) {
    return (
      <PhoneFrame top={top}>
        <NoSteps job={job} manualPage={manualPage} />
        {handover}
        <div className="done-btn">
          <Link className="btn pri" href={close}>
            <SquareCheck size={24} aria-hidden />
            ทำเสร็จแล้ว ปิดงาน
          </Link>
        </div>
        <p className="prov">
          <Th>{job.reason}</Th>
          {job.eta_text && (
            <>
              {" · "}
              <Th>{job.eta_text}</Th>
            </>
          )}
        </p>
        <div className="after">
          <HandoverForm workOrder={job.ref} />
        </div>
      </PhoneFrame>
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

  // Other pages the step sends the technician to - "the lockout procedure on
  // page 2" - checked against what the index read of the same manual. A page it
  // never saw is said to be missing rather than offered as a link to nothing.
  const named = await Promise.all(
    pagesNamed(`${current.text} ${current.text_th ?? ""}`, current.page).map(async (page) => {
      const read = await evidence(current.source_doc, page).catch(() => undefined);
      return { page, missing: read === null || read?.outcome === "not_indexed" };
    }),
  );

  return (
    <PhoneFrame top={top}>
      {handover}
      {job.playbook_warning !== null && (
        <div className="callout is-bad v-note">
          <CircleAlert size={20} aria-hidden />
          <div>
            <b>คู่มือเพิ่งถูกเปลี่ยน</b> · ขั้นตอนชุดนี้รอวิศวกรตรวจใหม่ ให้เทียบกับคู่มือก่อน
          </div>
        </div>
      )}

      <div className="v-progress" aria-hidden>
        <span className="v-big">
          <b>{at}</b>
          <small>/{total}</small>
        </span>
        <span className="rail">
          {job.steps.map((_, index) => {
            const n = index + 1;
            return (
              <span key={n} className={n < at ? "is-done" : n === at ? "cur" : undefined}>
                {n < at ? <Check size={18} strokeWidth={3} /> : n}
              </span>
            );
          })}
        </span>
      </div>

      <section className="v-card step" aria-labelledby="step-h">
        <p className="muted" id="step-h">
          ขั้นที่ {at} จาก {total}
        </p>
        <p className="th">
          <Th>{current.text_th ?? current.text}</Th>
        </p>
        {/* The cited page inside the job, one tap back to this step (third trial). */}
        <Link className="mref" href={manualPage(current.source_doc, current.page, at)}>
          <span className="thumb">
            <BookOpen size={28} aria-hidden />
          </span>
          <span className="t">
            อ่านคู่มือหน้า {current.page}
            {current.manual !== null && <small lang="en">{current.manual}</small>}
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
              ต้นฉบับจากคู่มือ · หน้า {current.page}
            </span>
            {current.text}
          </p>
        )}
      </section>

      <div className="done-btn">
        {last ? (
          <Link className="btn pri" href={close}>
            <SquareCheck size={24} aria-hidden />
            ครบทุกขั้น ปิดงาน
          </Link>
        ) : (
          <Link className="btn pri" href={`?step=${at + 1}`}>
            <Check size={24} aria-hidden />
            ทำขั้นนี้แล้ว ถัดไป
          </Link>
        )}
      </div>

      <nav className="after rows" aria-label="ทางเลือกอื่น">
        {at > 1 && (
          <Row icon={<ArrowLeft size={24} aria-hidden />} label={`ย้อนไปขั้นที่ ${at - 1}`} sub="ดูขั้นก่อนหน้าอีกครั้ง" href={`?step=${at - 1}`} />
        )}
        {!last && (
          <Row icon={<SquareCheck size={24} aria-hidden />} label="ปิดงานก่อนครบทุกขั้น" sub={`ทำถึงขั้นที่ ${at} จาก ${total}`} href={`${close}?reached=${at}`} />
        )}
        <Row icon={<ArrowRight size={24} aria-hidden />} label="กลับไปที่ใบงาน" sub="เหตุผล เครื่องมือ และงานถัดไป" href="/work" />
      </nav>
      <details className="sheet after">
        <summary>
          <ListOrdered size={24} aria-hidden />
          ดูทุกขั้น ({total})
        </summary>
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
      </details>
      <div className="after">
        <HandoverForm workOrder={job.ref} />
      </div>
    </PhoneFrame>
  );
}

/**
 * A job with no approved steps (REQ-H-08, principle 5): saying so beats inventing
 * a procedure, and the manual pages that might help are offered as pages to read.
 */
function NoSteps({ job, manualPage }: { job: Ticket; manualPage: (doc: string, page: number) => string }) {
  const where = job.where_to_look ?? [];
  return (
    <>
      <Plate station={job.station} title={job.machine_id} sub={<Th>{job.title?.replace(job.machine_id, "").trim() ?? job.reason}</Th>} />
      <div className="callout is-lock v-note" role="note">
        <CircleAlert size={20} aria-hidden />
        <div>
          <b>
            {job.origin === "scheduled"
              ? "ยังไม่มีขั้นตอนที่อนุมัติแล้วสำหรับงานนี้"
              : "ยังไม่มีขั้นตอนซ่อมที่อนุมัติแล้วสำหรับอาการนี้"}
          </b>
          <p>ให้ดูคู่มือของเครื่อง หรือโทรถามวิศวกร อย่าเดาขั้นตอนเอง</p>
        </div>
      </div>
      {where.length > 0 && (
        <nav className="sec rows" aria-label="ดูที่นี่">
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
    </>
  );
}

import { ArrowLeft, CircleAlert, ExternalLink, RefreshCw } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { NotThere, Shell } from "@/app/ui/shell";
import { Clock, PhoneFrame, Th } from "@/app/ui/v2/frame";
import { evidence } from "@/lib/review";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { currentRound, ticketAt } from "@/lib/work";

// Why there is no text, in a technician's words. The same three outcomes the
// API distinguishes (documents.py), because each has a different next move.
const NO_TEXT: Record<string, string> = {
  no_text: "หน้านี้เป็นภาพสแกน ระบบอ่านตัวอักษรไม่ได้ ให้เปิดไฟล์คู่มือดูภาพของหน้า",
  unreadable: "หน้านี้ในไฟล์เสีย ระบบอ่านไม่ได้ ให้ถามวิศวกร",
  not_indexed: "ระบบยังไม่ได้อ่านหน้านี้ของคู่มือ ให้เปิดไฟล์คู่มือ หรือถามวิศวกร",
};

/**
 * The page a step cites, read inside the job rather than in another tab.
 *
 * The third trial's technician tapped "open the manual at page 4" and landed in
 * a new browser tab with a 40-page PDF, and on a phone the way back to step 3 of
 * 6 was the tab switcher. Here the page's text - the same text the drafter
 * selected from and the engineer approved against - is on this screen, with one
 * tap back to the step it came from. The PDF stays one tap further for the
 * figures and tables text cannot carry. A page that cannot be read says so and
 * keeps the way back (REQ-H-11): never an empty page.
 */
export default async function ManualPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string }>;
  searchParams: Promise<{ doc?: string; page?: string; step?: string }>;
}) {
  const account = await requireAccount();
  const { ref } = await params;
  const { doc, page, step } = await searchParams;

  const [job, round] = await Promise.all([ticketAt(decodeURIComponent(ref)), currentRound()]);
  if (job === null) {
    return (
      <Shell account={account} current="/work">
        <NotThere home={homeFor(account.role)} what="ไม่พบใบงานนี้" />
      </Shell>
    );
  }
  const at = Number(page);
  if (doc === undefined || !Number.isInteger(at) || at < 1) {
    notFound();
  }

  const steps = `/work/${encodeURIComponent(job.ref)}/steps`;
  const back = step === undefined ? steps : `${steps}?step=${encodeURIComponent(step)}`;
  const backLabel = step === undefined ? "กลับไปที่ใบงาน" : `กลับไปขั้นที่ ${step}`;
  // The manual's name from the ticket, so even a page that failed to load says which manual it was.
  const manual = job.steps.find((one) => one.source_doc === doc)?.manual ?? job.where_to_look?.find((one) => one.document_id === doc)?.manual ?? null;
  const pdf = `/manual/${encodeURIComponent(doc)}#page=${at}`;
  const top = (
    <>
      <Link className="back" href={back}>
        <ArrowLeft size={24} aria-hidden />
        {backLabel}
      </Link>
      <span style={{ flex: 1 }} />
      <Clock now={new Date()} timezone={round.timezone} date={false} />
    </>
  );

  // A dropped Wi-Fi or a busy server: the page says what failed and keeps the way back.
  const read = await evidence(doc, at).catch(() => undefined);
  if (read === undefined) {
    return (
      <PhoneFrame top={top}>
        <div className="v-card" role="alert" style={{ marginTop: 16 }}>
          <h1 className="sym">
            <Th>{`โหลดหน้า ${at} ของ${manual ? ` ${manual} ` : "คู่มือ"}ไม่ได้`}</Th>
          </h1>
          <p style={{ marginTop: 8 }}>เชื่อมต่อระบบไม่ได้ตอนนี้ · ขั้นที่ทำแล้วยังอยู่ในใบงาน</p>
          <div className="done-btn">
            <Link className="btn pri" href={`?doc=${encodeURIComponent(doc)}&page=${at}${step ? `&step=${encodeURIComponent(step)}` : ""}`}>
              <RefreshCw size={24} aria-hidden />
              ลองโหลดใหม่
            </Link>
          </div>
          <div style={{ marginTop: 8 }}>
            <Link className="btn" href={back} style={{ background: "var(--sunk)" }}>
              <ArrowLeft size={24} aria-hidden />
              {backLabel}
            </Link>
          </div>
        </div>
      </PhoneFrame>
    );
  }
  if (read === null) {
    notFound();
  }

  // The index joins a page's lines, so a procedure arrives as one run of
  // "... 1. Isolate ... 2. Remove ...". Each numbered item goes back on its own
  // line - only after a sentence ends (fourth trial) - and nothing else is changed.
  const paragraphs = (read.text ?? "")
    .split(/\n{2,}/)
    .flatMap((one) => one.split(/(?<=\.)\s(?=\d{1,2}\.\s)/))
    .filter((one) => one.trim() !== "");

  return (
    <PhoneFrame top={top}>
      <p className="mhead">
        <b lang="en">{read.title}</b>
        {step === undefined ? `หน้า ${read.page} · เปิดจากใบงาน ${job.ref}` : `หน้า ${read.page} · เปิดจากขั้น ${step} ของ ${job.ref}`}
      </p>
      {read.withdrawn && (
        <div className="callout is-bad v-note">
          <CircleAlert size={20} aria-hidden />
          <div>
            <b>คู่มือฉบับนี้ถูกถอนแล้ว</b> · ให้ถามวิศวกรว่าฉบับที่ใช้อยู่คือฉบับไหน
          </div>
        </div>
      )}
      <section className="v-card page-text" style={{ marginTop: 12 }}>
        {paragraphs.length > 0 ? (
          <div lang="en">
            {paragraphs.map((text, index) => (
              <p key={index}>{text}</p>
            ))}
          </div>
        ) : (
          <p>
            <Th>{NO_TEXT[read.outcome] ?? NO_TEXT.not_indexed}</Th>
          </p>
        )}
      </section>
      <p className="prov">ข้อความที่ระบบอ่านจากคู่มือ รูปและตารางอาจไม่ครบ ถ้าขั้นตอนอ้างรูป ให้เปิดไฟล์คู่มือ</p>
      <div className="done-btn">
        <Link className="btn pri" href={back}>
          <ArrowLeft size={24} aria-hidden />
          {backLabel}
        </Link>
      </div>
      <nav className="after rows" aria-label="ทางเลือกอื่น">
        <a className="rw" href={pdf} target="_blank" rel="noreferrer">
          <ExternalLink size={24} aria-hidden />
          <span className="t">
            เปิดไฟล์คู่มือหน้า {at}
            <small>แท็บใหม่ · ดูรูปและตาราง</small>
          </span>
        </a>
      </nav>
    </PhoneFrame>
  );
}

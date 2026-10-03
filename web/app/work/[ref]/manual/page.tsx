import Link from "next/link";
import { notFound } from "next/navigation";

import { NotThere, Shell } from "@/app/ui/shell";
import { evidence } from "@/lib/review";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import { ticketAt } from "@/lib/work";

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
 * The third trial's technician tapped "open the manual at page 4" and landed
 * in a new browser tab with a 40-page PDF, and on a phone the way back to step
 * 3 of 6 was the tab switcher. Here the page's text - the same text the
 * drafter selected from and the engineer approved against - is on this screen,
 * with one tap back to the step it came from. The PDF stays one tap further
 * for the figures and tables text cannot carry.
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

  const job = await ticketAt(decodeURIComponent(ref));
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

  const read = await evidence(doc, at);
  if (read === null) {
    notFound();
  }

  const steps = `/work/${encodeURIComponent(job.ref)}/steps`;
  const back = step === undefined ? steps : `${steps}?step=${encodeURIComponent(step)}`;
  const pdf = `/manual/${encodeURIComponent(doc)}#page=${at}`;
  // The index joins a page's lines, so a procedure arrives as one run of
  // "... 1. Isolate ... 2. Remove ...". Each numbered item goes back on its own
  // line - the way the page itself sets it out - and nothing else is changed.
  const paragraphs = (read.text ?? "")
    .split(/\n{2,}/)
    .flatMap((one) => one.split(/\s(?=\d{1,2}\.\s)/))
    .filter((one) => one.trim() !== "");

  return (
    <Shell account={account} current="/work">
      <div className="who">
        <Link href={back}>‹ {step === undefined ? "กลับไปที่ใบงาน" : `กลับไปขั้นที่ ${step}`}</Link>
        <span className="muted">ใบงาน {job.ref}</span>
      </div>

      <section className="card manual-page">
        <h2>
          {read.title} <span className="muted">· หน้า {read.page}</span>
        </h2>
        {read.withdrawn && <p className="warning">⚠️ คู่มือฉบับนี้ถูกถอนแล้ว ให้ถามวิศวกรว่าฉบับที่ใช้อยู่คือฉบับไหน</p>}
        {paragraphs.length > 0 ? (
          <div lang="en">
            {paragraphs.map((text, index) => (
              <p key={index}>{text}</p>
            ))}
          </div>
        ) : (
          <p className="warning">{NO_TEXT[read.outcome] ?? NO_TEXT.not_indexed}</p>
        )}
        <p className="muted">ข้อความที่ระบบอ่านจากคู่มือ รูปและตารางอาจไม่ครบ ถ้าขั้นตอนอ้างรูป ให้เปิดไฟล์คู่มือ</p>
      </section>

      <Link className="button-link big ok" href={back}>
        ‹ {step === undefined ? "กลับไปที่ใบงาน" : `กลับไปขั้นที่ ${step}`}
      </Link>
      <a className="button-link quiet" href={pdf} target="_blank" rel="noreferrer">
        📄 เปิดไฟล์คู่มือหน้า {at} (แท็บใหม่)
      </a>
    </Shell>
  );
}

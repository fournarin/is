import { NotYours, Shell } from "@/app/ui/shell";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Decisions } from "@/app/review/[proposalId]/decisions";
import { flagSteps, locate } from "@/lib/drafts";
import { evidence, proposal } from "@/lib/review";
import { homeFor } from "@/lib/screens";
import { ROLE_NAMES, requireAccount } from "@/lib/session";

/**
 * One proposal: the draft on the left, the page it was taken from on the right.
 *
 * No modal, and the evidence is not behind a tap. If a reviewer has to open a
 * PDF for every proposal, minutes-per-proposal climbs and people start waving
 * drafts through - which turns ADR-003's engineer-in-the-way from a control
 * into a formality (ADR-064).
 *
 * Which step's evidence is shown is a query parameter rather than client state,
 * so the panel arrives rendered with the page. On a laptop the two sit side by
 * side; on a phone the evidence follows the steps down the page, which is the
 * same reading order.
 */
const OUTCOME: Record<string, string> = {
  repair: "ขั้นตอนซ่อม",
  diagnostic: "ไล่หาสาเหตุ",
  not_found: "ไม่พบในคู่มือ",
};

export default async function ProposalPage({
  params,
  searchParams,
}: {
  params: Promise<{ proposalId: string }>;
  searchParams: Promise<{ step?: string }>;
}) {
  const account = await requireAccount();
  // The same people as the queue itself. Without this the API's 403 surfaced
  // as "A server error occurred" to anybody who followed a kept link.
  if (account.role !== "engineer" && account.role !== "supervisor") {
    return (
      <Shell account={account} current="/review">
        <NotYours home={homeFor(account.role)} what="หน้านี้เป็นของวิศวกร" />
      </Shell>
    );
  }
  const { proposalId } = await params;
  const id = Number(proposalId);
  if (!Number.isInteger(id) || id <= 0) {
    notFound();
  }

  const draft = await proposal(id);
  const steps = flagSteps(draft.steps);
  const asked = Number((await searchParams).step ?? 0);
  const chosen = Number.isInteger(asked) && asked >= 0 && asked < steps.length ? asked : 0;
  const step = steps[chosen];
  const page = step === undefined ? null : await evidence(step.source_doc, step.page);
  const found = page?.text != null && step !== undefined ? locate(page.text, step.text) : null;

  return (
    <Shell account={account} current="/review">
      <div className="who">
        <span>
          <Link href={`/review?model=${encodeURIComponent(draft.machine_model)}`}>คิวรีวิว</Link>
          <span className="muted">
            {" "}
            · {draft.machine_model} · {ROLE_NAMES[account.role]}
          </span>
        </span>
      </div>

      <h1>
        {draft.symptom_code}
        <span className="muted"> · {draft.origin === "technician" ? "ช่างแย้ง" : (OUTCOME[draft.outcome] ?? draft.outcome)}</span>
      </h1>
      <p className="muted">{draft.reason}</p>

      {draft.status !== "pending" && (
        <p className="warning">
          ใบนี้ถูกตัดสินไปแล้ว ({draft.status}) — ดูได้ แต่ตัดสินซ้ำไม่ได้
        </p>
      )}

      <div className="two-up">
        <section className="card">
          <h2>ร่าง</h2>
          {steps.length === 0 ? (
            <p className="muted">
              ร่างนี้ไม่มีขั้นตอน — ระบบจึงไม่ส่งร่างนี้ให้ใช้ทั้งฉบับ
            </p>
          ) : (
            <ol className="draft">
              {steps.map((one, index) => (
                <li key={index} className={index === chosen ? "current" : undefined}>
                  <Link href={`?step=${index}`} scroll={false}>
                    <span className="step-body">{one.text}</span>
                    <span className="cite">
                      หน้า {one.page}
                      {/* At page level a mixed draft looks ordinary; at step
                          level it reports itself (ADR-015). */}
                      {one.odd_document && <strong className="pending"> คนละเอกสาร</strong>}
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          )}

          {draft.rejected.length > 0 && (
            <details>
              <summary>ขั้นตอนที่ถูกกันออก ({draft.rejected.length})</summary>
              <ul className="next">
                {draft.rejected.map((one, index) => (
                  <li key={index} className="muted">
                    {JSON.stringify(one)}
                  </li>
                ))}
              </ul>
              <p className="muted">
                ระบบกันไว้เพราะไม่ผ่านการตรวจตัวเลขหรือไม่ตรงกับข้อความในหน้านั้น
                คนที่บอกได้ว่าคู่มือผิดหรือ backend ผิด คือคนที่กำลังอ่านอยู่นี่
              </p>
            </details>
          )}

          {draft.tools.length > 0 && <p className="muted">เครื่องมือ: {draft.tools.join(", ")}</p>}
        </section>

        <section className="card evidence">
          <h2>หลักฐาน</h2>
          {step === undefined ? (
            <p className="muted">ไม่มีขั้นตอนให้เทียบ</p>
          ) : page === null ? (
            <p className="muted">
              ไม่พบเอกสารที่ขั้นตอนนี้อ้างถึงในระบบแล้ว — ตรวจกับคู่มือฉบับจริงก่อนอนุมัติ
            </p>
          ) : (
            <>
              <p className="muted">
                {page.title} · หน้า {page.page}
                {page.edition !== null && ` · ${page.edition}`}
              </p>
              {/* The line ADR-015 does not relax: a candidate from another
                  machine model is labelled, never mixed in silently. */}
              {page.machine_model !== draft.machine_model && (
                <p className="warning">
                  หน้านี้มาจากคู่มือของรุ่น {page.machine_model} ไม่ใช่ {draft.machine_model}
                </p>
              )}
              {page.withdrawn && <p className="warning">คู่มือฉบับนี้ถูกถอนออกจากการใช้งานแล้ว</p>}

              {page.text === null ? (
                <p className="muted">
                  {page.outcome === "not_indexed"
                    ? `หน้า ${page.page} ยังไม่ได้ถูก ingest เข้าดัชนี — เทียบกับไฟล์คู่มือเองก่อนอนุมัติ`
                    : `หน้านี้ไม่มีข้อความในดัชนี (${page.outcome}) — มักเป็นหน้าสแกน ต้องเปิดคู่มือดูเอง`}
                </p>
              ) : found === null ? (
                <>
                  <p className="warning">
                    หาข้อความของขั้นตอนนี้ในหน้าดังกล่าวไม่พบ — ตรวจกับคู่มือก่อนอนุมัติ
                  </p>
                  <pre className="page">{page.text}</pre>
                </>
              ) : (
                <pre className="page">
                  {found.before}
                  <mark>{found.match}</mark>
                  {found.after}
                </pre>
              )}

              {/* A range request, so this opens at the page rather than
                  downloading the volume (ADR-019). */}
              <a
                className="button-link quiet"
                href={`/manual/${encodeURIComponent(page.document_id)}#page=${page.page}`}
                target="_blank"
                rel="noreferrer"
              >
                เปิดคู่มือที่หน้า {page.page}
              </a>
            </>
          )}
        </section>
      </div>

      {account.role === "engineer" && draft.status === "pending" ? (
        <Decisions
          proposalId={draft.proposal_id}
          steps={draft.steps.map((one) => one.text)}
          proposedSkill={draft.proposed_skill}
          proposedMinutes={draft.proposed_minutes}
        />
      ) : (
        <p className="muted">
          {account.role === "engineer"
            ? "ใบที่ตัดสินแล้วแก้ไม่ได้ — ประวัติคือหลักฐานว่าตอนนั้นระบบสั่งอะไร"
            : "การอนุมัติเป็นของวิศวกรเท่านั้น"}
        </p>
      )}
    </Shell>
  );
}

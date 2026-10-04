import { NotYours, Shell } from "@/app/ui/shell";
import { homeFor } from "@/lib/screens";
import Link from "next/link";

import { groupByModel } from "@/lib/drafts";
import { ROLE_NAMES, requireAccount } from "@/lib/session";
import { reviewQueue } from "@/lib/review";

/**
 * The review queue, one machine model at a time.
 *
 * Grouping is the whole layout decision here. Reviewing an R-2000iC draft and
 * an M-710iC draft alternately means holding two manuals in mind at once, and
 * that is where a step from the wrong model gets waved through - the one thing
 * ADR-015's recall setting does not relax about (ADR-064).
 *
 * A supervisor may look and may not decide. That is not a softer version of the
 * same permission: a supervisor who cannot see the queue cannot ask why it is
 * not moving, which is their job, and the endpoints refuse them either way
 * (invariant 6).
 */
const OUTCOME: Record<string, string> = {
  repair: "ขั้นตอนซ่อม",
  diagnostic: "ไล่หาสาเหตุ",
  not_found: "ไม่พบในคู่มือ",
};

export default async function ReviewQueuePage({
  searchParams,
}: {
  searchParams: Promise<{ model?: string; done?: string }>;
}) {
  const account = await requireAccount();
  if (account.role !== "engineer" && account.role !== "supervisor") {
    return (
      <Shell account={account} current="/review">
        <NotYours home={homeFor(account.role)} what="หน้านี้เป็นของวิศวกร" />
      </Shell>
    );
  }

  const groups = groupByModel(await reviewQueue());
  const { model: asked, done } = await searchParams;
  // What the last press did, said once on the page it lands on: the fourth
  // trial's engineer approved and dismissed and was shown nothing either time.
  const doneLine =
    done === "approved"
      ? "อนุมัติแล้ว ใบงานที่เปิดอยู่ของอาการนี้ซึ่งยังไม่มีขั้นตอนจะได้ขั้นตอนชุดนี้"
      : done === "returned"
        ? "ตีกลับแล้ว ระบบจะร่างใหม่โดยใช้สิ่งที่คุณเขียนเป็นคำถาม"
        : done === "dismissed"
          ? "ปิดร่างนี้แล้ว เหตุผลของคุณถูกบันทึกไว้"
          : null;
  const shown =
    groups.find((group) => group.machine_model === asked) ?? groups[0];

  return (
    <Shell account={account} current="/review">
      <div className="who">
        <span>
          คิวรีวิว
          <span className="muted"> · {ROLE_NAMES[account.role]}</span>
        </span>
      </div>

      {doneLine && <p className="recorded">{doneLine}</p>}

      {groups.length === 0 ? (
        <p className="card">
          ไม่มีใบรออนุมัติในคิวตอนนี้ — ร่างใหม่จะขึ้นมาเองเมื่อระบบร่างเสร็จ
        </p>
      ) : (
        <>
          <nav className="tabs" aria-label="เลือกรุ่นเครื่อง">
            {groups.map((group) => (
              <Link
                key={group.machine_model}
                href={`/review?model=${encodeURIComponent(group.machine_model)}`}
                className={
                  group.machine_model === shown.machine_model
                    ? "tab current"
                    : "tab"
                }
                aria-current={
                  group.machine_model === shown.machine_model
                    ? "page"
                    : undefined
                }
              >
                {group.machine_model} ({group.proposals.length})
              </Link>
            ))}
          </nav>

          {/* A "not found" result has nothing to approve, and the third trial's
              engineer read it as a draft waiting for a signature. It is a gap
              in the manuals that needs a decision, so it is listed as one. */}
          {[
            {
              title: "รออนุมัติ",
              rows: shown.proposals.filter((one) => one.outcome !== "not_found"),
              note: null,
            },
            {
              title: "คู่มือไม่มีคำตอบ ต้องตัดสินใจ",
              rows: shown.proposals.filter((one) => one.outcome === "not_found"),
              note: "ไม่มีขั้นตอนให้อนุมัติ ระบบค้นคู่มือแล้วไม่พบเรื่องนี้ เปิดดูแล้วเลือก: ตีกลับพร้อมคำถามที่ชัดขึ้น (เช่น บอกหน้าที่น่าจะมี) หรือปิดใบพร้อมเหตุผลถ้าคู่มือไม่มีเรื่องนี้จริง ระหว่างนี้ช่างจะเห็นว่ายังไม่มีขั้นตอน ให้ดูคู่มือหรือถามวิศวกร",
            },
          ]
            .filter((section) => section.rows.length > 0)
            .map((section) => (
              <section key={section.title}>
                <h2>
                  {section.title} ({section.rows.length})
                </h2>
                {section.note !== null && <p className="muted">{section.note}</p>}
                {section.rows.map((one) => (
                <article className="card" key={one.proposal_id}>
                  <div className="screen-head">
                    <h3>
                      <Link href={`/review/${one.proposal_id}`}>
                        {one.symptom_title ?? one.symptom_code}
                      </Link>
                    </h3>
                    <span className="muted">
                      {one.origin === "technician"
                        ? "ช่างแย้ง"
                        : `ร่าง · ${OUTCOME[one.outcome] ?? one.outcome}`}
                    </span>
                  </div>
                  <p className="muted">
                    {one.machine_model} · {one.symptom_code} · {one.reason}
                  </p>
                  <p className="muted">
                    {one.outcome === "not_found" ? "ไม่มีขั้นตอน" : `${one.steps} ขั้นตอน`}
                    {/* Shown rather than hidden: a draft that lost three steps to
                        the figure gate is a different thing from one that never had
                        them, and only the reviewer can tell which (ADR-037). */}
                    {one.rejected > 0 && ` · ถูกกันออก ${one.rejected} ขั้นตอน`}
                    {one.created_by !== null && ` · โดย ${one.created_by}`}
                  </p>
                </article>
                ))}
              </section>
            ))}
        </>
      )}

      {account.role === "supervisor" && (
        <p className="muted">
          {/* Invariant 6: the API refuses it, the button is not merely hidden. */}
          หัวหน้ากะดูคิวได้เพื่อจะได้ถามว่าทำไมคิวไม่ขยับ
          แต่การอนุมัติเป็นของวิศวกรเท่านั้น
        </p>
      )}
    </Shell>
  );
}

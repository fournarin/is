import { KeepFresh } from "@/app/ui/keep-fresh";
import { NotYours, Shell } from "@/app/ui/shell";
import { bandFor } from "@/lib/display";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";
import {
  activeWork,
  currentRound,
  finishedThisShift,
  proposals,
  ticket,
  type Ticket,
} from "@/lib/work";

const STATUS: Record<string, string> = {
  assigned: "มอบหมายแล้ว",
  in_progress: "กำลังทำ",
  handed_over: "ส่งต่อรอคนรับ",
};

/**
 * The shift lead's whiteboard (ADR-093): what is waiting for them, what the
 * system is holding back, and what the floor is on - three columns, as on the
 * board in the maintenance office.
 *
 * Nothing here ranks, scores or phrases anything. The order of each column is
 * the order the API gave, and every sentence was written by the backend
 * (ADR-005, ADR-063). Confirming is one tap and setting aside asks why, because
 * agreeing with the scheduler explains itself and disagreeing does not
 * (ADR-071). A job set aside stays aside for the shift and has its own column,
 * so "not now" visibly does something (ADR-120).
 */
export default async function BoardPage({
  searchParams,
}: {
  searchParams: Promise<{
    released?: string;
    confirmed?: string;
    rejected?: string;
    brought?: string;
    error?: string;
  }>;
}) {
  const account = await requireAccount();
  if (account.role !== "supervisor" && account.role !== "engineer") {
    return (
      <Shell account={account} current="/board">
        <NotYours
          home={homeFor(account.role)}
          what="กระดานงานเป็นของหัวหน้ากะ"
        />
      </Shell>
    );
  }
  const { released, confirmed, rejected, brought, error } = await searchParams;

  const [round, waiting, active, finished] = await Promise.all([
    currentRound(),
    proposals(),
    activeWork(),
    finishedThisShift(),
  ]);
  const tickets = new Map<string, Ticket>(
    await Promise.all(
      [
        ...waiting.map((one) => one.ref),
        ...round.held.map((one) => one.ref),
        ...round.set_aside.map((one) => one.ref),
      ].map(async (ref) => [ref, await ticket(ref)] as const),
    ),
  );
  const load =
    round.load_ratio === null ? null : Math.round(round.load_ratio * 100);

  return (
    <Shell account={account} current="/board">
      <KeepFresh />
      <h1>กระดานงานกะนี้</h1>
      <p className="muted">
        ระบบเลือกช่างให้แต่ละงานแล้ว กด “ยืนยัน” เพื่อส่งงานถึงช่าง หรือ
        “พักไว้ก่อน” ถ้ายังไม่ควรทำตอนนี้
      </p>

      {confirmed !== undefined && (
        <p className="recorded">
          ✓ ยืนยัน {confirmed} แล้ว งานถูกส่งถึงช่างแล้ว
        </p>
      )}
      {rejected !== undefined && (
        <p className="recorded">
          ⏸ พัก {rejected} ไว้แล้ว ระบบจะไม่เสนองานนี้อีกในกะนี้ จนกว่าคุณจะกด
          “นำกลับมา”
        </p>
      )}
      {brought !== undefined && (
        <p className="recorded">
          ↩ นำ {brought} กลับมาแล้ว ระบบจะเลือกช่างให้ในรอบถัดไป (ไม่เกิน 5
          นาที)
        </p>
      )}
      {released !== undefined && (
        <p className="recorded">
          ✓ ปล่อย {released} แล้ว ระบบจะเลือกช่างให้ในรอบถัดไป (ไม่เกิน 5 นาที)
        </p>
      )}
      {error !== undefined && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div className="stats">
        <div className="stat">
          <div className="label">ภาระงานของกะ</div>
          <div className="big-number">{load === null ? "—" : `${load}%`}</div>
          <div className={`meter ${round.band}`}>
            <span style={{ width: `${Math.min(load ?? 0, 100)}%` }} />
          </div>
        </div>
        <div className="stat">
          <div className="label">รอคุณยืนยัน</div>
          <div className="big-number">{waiting.length}</div>
        </div>
        <div className="stat">
          <div className="label">ส่งถึงช่างแล้ว</div>
          <div className="big-number">{active.length}</div>
        </div>
      </div>
      {/* The round's summary is about what the next round would add; it cannot
          see the cards already waiting here, and "nothing new" beside three
          waiting cards read as a contradiction (trial 5). */}
      <p className="muted">
        {waiting.length > 0 && round.summary.includes("ไม่มีงานใหม่ที่จะเสนอ")
          ? `${round.summary} นอกจากที่รอคุณยืนยันอยู่`
          : round.summary}
      </p>

      <div className="board">
        <section className="column">
          <h2>
            รอคุณยืนยัน <span className="count">{waiting.length}</span>
          </h2>
          {waiting.length === 0 && <p className="muted">ไม่มีงานรอยืนยัน</p>}
          {round.placed.length > 0 && (
            // Queued work the next round will propose, so a new report or a job
            // brought back is on the board before the round runs (ADR-126).
            <p className="muted">
              รอบถัดไป (ไม่เกิน 5 นาที) ระบบจะเสนออีก {round.placed.length} งาน
            </p>
          )}
          {/* Most important first, by the score that ranked them. In arrival
              order an urgent report losing 180 units sat third, under a
              medium job losing 37, with nothing saying why (fourth trial). */}
          {[...waiting]
            .sort((a, b) => b.priority_score - a.priority_score || a.ref.localeCompare(b.ref))
            .map((one) => {
            const job = tickets.get(one.ref)!;
            const band = bandFor(job);
            return (
              <article className={`ticket ${band.tone}`} key={one.ref}>
                <div className="ticket-head">
                  <span className="machine-small">{job.machine_id}</span>
                  <span className={`pill ${band.tone}`}>{band.label}</span>
                </div>
                <p>{job.reason}</p>
                {job.eta_text && <p>{job.eta_text}</p>}
                <p>
                  👷 ส่งให้ <strong>{one.assignee_names.join(", ")}</strong>
                </p>
                {job.handover_note && (
                  <p className="warning">
                    ↪ ช่างคนก่อนส่งต่อไว้: {job.handover_note}
                  </p>
                )}
                <p className="muted">ทำไมก่อน: {one.priority_reason}</p>
                <div className="actions">
                  <form method="post" action="/overview/confirm">
                    <input type="hidden" name="ref" value={one.ref} />
                    <button type="submit" className="ok">
                      ✓ ยืนยัน
                    </button>
                  </form>
                  <details>
                    <summary>⏸ พักไว้ก่อน</summary>
                    <form method="post" action="/overview/reject">
                      <input type="hidden" name="ref" value={one.ref} />
                      <p className="muted">
                        งานจะไปอยู่ในช่อง “คุณพักไว้” และไม่ถูกเสนออีกจนจบกะ
                        หรือจนกว่าคุณจะนำกลับมา
                      </p>
                      <label className="field">
                        <span>ทำไมยังไม่ควรทำตอนนี้</span>
                        <textarea
                          name="reason"
                          rows={2}
                          required
                          placeholder="เช่น รอหยุดสายตอนพักเที่ยง"
                        />
                      </label>
                      <button type="submit" className="danger">
                        พักไว้ พร้อมเหตุผลนี้
                      </button>
                    </form>
                  </details>
                </div>
              </article>
            );
          })}
        </section>

        {round.set_aside.length > 0 && (
          <section className="column">
            <h2>
              คุณพักไว้ <span className="count">{round.set_aside.length}</span>
            </h2>
            {round.set_aside.map((one) => {
              const job = tickets.get(one.ref)!;
              const band = bandFor(job);
              return (
                <article
                  className={`ticket ${band.tone}`}
                  key={`aside-${one.ref}`}
                >
                  <div className="ticket-head">
                    <span className="machine-small">{job.machine_id}</span>
                    <span className={`pill ${band.tone}`}>{band.label}</span>
                  </div>
                  <p>{job.reason}</p>
                  {job.eta_text && <p>{job.eta_text}</p>}
                  <p className="muted">เหตุผลที่พัก: {one.why}</p>
                  <form method="post" action="/overview/bring-back">
                    <input type="hidden" name="ref" value={one.ref} />
                    <button type="submit">↩ นำกลับมาให้ระบบจัดช่าง</button>
                  </form>
                </article>
              );
            })}
          </section>
        )}

        <section className="column">
          <h2>
            ระบบกันไว้ก่อน{" "}
            <span className="count">
              {round.held.length + round.unassigned.length}
            </span>
          </h2>
          {round.unassigned.map((one) => (
            // Admitted by the gate with nobody free to take it (ADR-102): on a
            // heavy shift this is where an urgent job waits, and it must show.
            <article className="ticket urgent" key={`free-${one.ref}`}>
              <div className="ticket-head">
                <span className="machine-small">{one.ref}</span>
                <span className="pill urgent">รอช่างว่าง</span>
              </div>
              <p className="muted">{one.why}</p>
            </article>
          ))}
          {round.held.length === 0 && round.unassigned.length === 0 && (
            <p className="muted">ไม่มีงานถูกกันไว้</p>
          )}
          {round.held.map((one) => {
            const job = tickets.get(one.ref)!;
            const band = bandFor(job);
            return (
              <article className={`ticket ${band.tone}`} key={one.ref}>
                <div className="ticket-head">
                  <span className="machine-small">{job.machine_id}</span>
                  <span className={`pill ${band.tone}`}>{band.label}</span>
                </div>
                <p>{job.reason}</p>
                {job.eta_text && <p>{job.eta_text}</p>}
                <p className="muted">ทำไมยังไม่ปล่อย: {one.why}</p>
                <details>
                  <summary>ปล่อยงานนี้เลย</summary>
                  {/* A plain form, posted and redirected: a release takes the
                      ticket out of this list (app/overview/release/route.ts). */}
                  <form method="post" action="/overview/release">
                    <input type="hidden" name="ref" value={one.ref} />
                    <label className="field">
                      <span>ทำไมต้องปล่อยตอนนี้</span>
                      <textarea
                        name="reason"
                        rows={2}
                        required
                        placeholder="เช่น สาย A หยุดรอชิ้นนี้อยู่"
                      />
                    </label>
                    <button type="submit">ปล่อยงาน พร้อมเหตุผลนี้</button>
                  </form>
                </details>
              </article>
            );
          })}
        </section>

        <section className="column">
          <h2>
            ส่งถึงช่างแล้ว <span className="count">{active.length}</span>
          </h2>
          {active.length === 0 && (
            <p className="muted">ยังไม่มีงานที่ส่งถึงช่าง</p>
          )}
          {active.map((one) => (
            <article className="ticket" key={one.ref}>
              <div className="ticket-head">
                <span className="machine-small">{one.machine_id}</span>
                <span
                  className={`pill ${one.status === "in_progress" ? "done" : ""}`}
                >
                  {STATUS[one.status] ?? one.status}
                </span>
              </div>
              <p>{one.reason}</p>
              {one.eta_text && <p>{one.eta_text}</p>}
              <p className="muted">
                👷 {one.assignee_names.join(", ") || "ยังไม่มีคนรับ"}
              </p>
            </article>
          ))}
        </section>

        <section className="column">
          <h2>
            เสร็จแล้วกะนี้ <span className="count">{finished.length}</span>
          </h2>
          {finished.length === 0 && (
            <p className="muted">ยังไม่มีงานที่ปิดในกะนี้</p>
          )}
          {finished.map((one) => (
            <article className="ticket" key={`done-${one.ref}`}>
              <div className="ticket-head">
                <span className="machine-small">{one.machine_id}</span>
                <span className="pill done">{one.outcome}</span>
              </div>
              <p>{one.reason}</p>
              <p className="muted">
                👷 {one.by_names.join(", ")} · ปิดเมื่อ {one.closed_when}
              </p>
              {one.note && <p className="muted">บันทึก: {one.note}</p>}
            </article>
          ))}
        </section>
      </div>
    </Shell>
  );
}

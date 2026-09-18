import Link from "next/link";

import { LineDiagram, LineFaults } from "@/app/overview/line-diagram";
import { plantDateTime, plantTime } from "@/lib/display";
import { gaps, lineOverview, machineHealth } from "@/lib/overview";
import { ROLE_NAMES, requireAccount } from "@/lib/session";
import { currentRound, proposals } from "@/lib/work";

/**
 * Where "monitor and predict" becomes something a person can point at.
 *
 * Every figure comes from `/overview/line`, `/overview/gaps` or
 * `/dispatch/round`. Nothing is computed here and no fourth endpoint exists to
 * summarise them: a screen with its own arithmetic is a second opinion about
 * the shift that nobody can reconcile with the first (ADR-050, ADR-063).
 *
 * The line it may not cross is operational state somebody can act on now. The
 * test for every element is one question - when this number is bad, who does
 * what immediately? A monthly chart has no answer; "six symptoms with no
 * playbook" answers instantly.
 */
export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{
    released?: string;
    confirmed?: string;
    rejected?: string;
    drafting?: string;
    already?: string;
    error?: string;
  }>;
}) {
  const account = await requireAccount();
  const { released, confirmed, rejected, drafting, already, error } =
    await searchParams;
  if (account.role !== "supervisor" && account.role !== "engineer") {
    return (
      <>
        <h1>ภาพรวมสายการผลิต</h1>
        <p className="card">
          หน้านี้เป็นของหัวหน้ากะและวิศวกร บัญชีนี้เป็น
          {ROLE_NAMES[account.role]}
        </p>
        <p>
          <Link href="/">กลับหน้าแรก</Link>
        </p>
      </>
    );
  }

  const [overview, unanswered, round, waiting, health] = await Promise.all([
    lineOverview(),
    gaps(),
    currentRound(),
    proposals(),
    machineHealth(),
  ]);
  const shift = overview.shift;
  const load =
    shift.load_ratio === null ? null : Math.round(shift.load_ratio * 100);

  return (
    <>
      <div className="who">
        <span>
          <Link href="/">‹ หน้าแรก</Link>
        </span>
        <span className="muted">
          อัปเดต {plantTime(overview.at, overview.timezone)}
        </span>
      </div>

      {overview.lines.map((line) => (
        <section key={line.line_id}>
          <h1>{line.line_id}</h1>
          <LineDiagram line={line} />
          <LineFaults line={line} timezone={overview.timezone} />
        </section>
      ))}

      {overview.unplaced_machines.length > 0 && (
        <p className="warning">
          เครื่องที่มีอาการแต่ยังไม่ได้อยู่ในผังสถานี วาดบนสายไม่ได้:{" "}
          {overview.unplaced_machines.join(", ")}
        </p>
      )}

      {/* Readable across a workshop: the load is the biggest thing on the page. */}
      <section className="card band">
        <p className="load">{load === null ? "—" : `${load}%`}</p>
        <p>{shift.summary}</p>
        <p className="muted">
          {shift.technicians_on_shift} ช่างในกะ · งานเปิดอยู่{" "}
          {shift.open_orders} ใบ · {shift.committed_minutes} จาก{" "}
          {shift.capacity_minutes} นาที
        </p>
      </section>

      <section>
        <h2>งานที่รอคุณยืนยัน ({waiting.length})</h2>

        {confirmed !== undefined && (
          <p className="recorded">
            ยืนยัน {confirmed} แล้ว — ส่งถึงช่างและออกไปยังปลายทางแล้ว
          </p>
        )}
        {rejected !== undefined && (
          <p className="recorded">
            ปฏิเสธ {rejected} แล้ว — กลับเข้าคิว รอบถัดไปจะจัดใหม่
          </p>
        )}
        {waiting.length === 0 ? (
          <p className="card">ไม่มีงานรอยืนยัน</p>
        ) : (
          // The list a shift lead works through, oldest first - the one nearest
          // expiry is the one nearest being decided by nobody (ADR-071 §6).
          <ul className="held-list">
            {waiting.map((one) => (
              <li className="held" key={one.ref}>
                <div>
                  <strong>{one.ref}</strong> → {one.assignees.join(", ")}
                  <br />
                  <span className="muted">{one.priority_reason}</span>
                  <br />
                  <span className="muted">
                    กลับเข้าคิวเองถ้าไม่ตอบภายใน{" "}
                    {plantTime(one.expires_at, overview.timezone)}
                  </span>
                </div>
                <div className="answer">
                  <form method="post" action="/overview/confirm">
                    <input type="hidden" name="ref" value={one.ref} />
                    <button type="submit">ยืนยัน</button>
                  </form>
                  <details>
                    <summary>ไม่ใช่งานนี้</summary>
                    <form method="post" action="/overview/reject">
                      <input type="hidden" name="ref" value={one.ref} />
                      <label className="field">
                        <span>ทำไมถึงยังไม่ควรส่ง</span>
                        <textarea
                          name="reason"
                          rows={2}
                          required
                          placeholder="เช่น ช่างคนนี้ติดงานที่สาย B อยู่"
                        />
                      </label>
                      <button type="submit" className="quiet">
                        ปฏิเสธพร้อมเหตุผลนี้
                      </button>
                    </form>
                  </details>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2>งานที่ประตูโหลดกั้นไว้ ({round.held.length})</h2>

        {released !== undefined && (
          <p className="recorded">ปล่อย {released} แล้ว — รอบถัดไปจะจัดคนให้</p>
        )}
        {error !== undefined && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {round.held.length === 0 ? (
          <p className="card">ตอนนี้ไม่มีงานถูกกั้น</p>
        ) : (
          // Named, not counted. ADR-011 requires the shift lead to be told what
          // is being held; held silently, the system looks like it forgot, and
          // that is how people stop trusting it.
          <ul className="held-list">
            {round.held.map((one) => (
              <li className="held" key={one.ref}>
                <div>
                  <strong>{one.ref}</strong>
                  <br />
                  <span className="muted">{one.why}</span>
                </div>
                <details>
                  <summary>ปล่อยงานนี้</summary>
                  {/* A plain form, posted and redirected. A release takes the
                      ticket out of this list, so anything held in the component
                      would vanish with it (app/overview/release/route.ts). */}
                  <form method="post" action="/overview/release">
                    <input type="hidden" name="ref" value={one.ref} />
                    <label className="field">
                      <span>ทำไมถึงต้องปล่อยตอนนี้</span>
                      <textarea
                        name="reason"
                        rows={2}
                        required
                        placeholder="เช่น สาย A หยุดรอชิ้นนี้อยู่"
                      />
                    </label>
                    <button type="submit" className="quiet">
                      ปล่อยพร้อมเหตุผลนี้
                    </button>
                  </form>
                </details>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Two lists and never one. The machines that have failed most over the
          observed span, and the machines with the worst thing standing open
          right now, are different questions with different answers - blending
          them into a single "health score" would hide which of the two moved
          (ADR-072 section 2, ADR-081).

          Nothing is computed here. Every figure is a field and every sentence
          was written by the backend; a reason assembled in TypeScript from the
          numbers beside it would be a second voice explaining them (ADR-063). */}
      <section>
        <h2>สุขภาพเครื่องจักร</h2>

        <p className="muted">
          {health.observed_from === null
            ? "ยังไม่มีใบงานที่ปิดแล้ว จึงยังไม่มีอะไรให้นับ"
            : `นับจากใบงานที่ปิดแล้วในช่วง ${plantDateTime(
                health.observed_from,
                overview.timezone,
              )} ถึง ${plantDateTime(health.observed_to ?? health.at, overview.timezone)} รวม ${Math.round(
                health.observed_days,
              )} วัน`}
        </p>

        <div className="health">
          <div className="card">
            <h3>เสียบ่อยที่สุดในช่วงที่นับ</h3>
            <ol className="health-list">
              {health.by_history.map((row) => (
                <li key={`history-${row.machine_id}`}>
                  <strong>{row.machine_id}</strong>{" "}
                  <span className="muted">
                    {row.history.failures_per_100_days === null
                      ? "ยังไม่มีช่วงเวลาให้หาร"
                      : `${row.history.failures_per_100_days.toFixed(1)} ครั้งต่อ 100 วัน`}
                  </span>
                  <br />
                  <span className="muted">{row.history.reason}</span>
                  {/* Displayed, never ranked on: a machine somebody was sent to
                      for nothing has a rule problem rather than a machine
                      problem (ADR-076 section 3). */}
                  {row.history.false_alarms > 0 && (
                    <>
                      <br />
                      <span className="muted">
                        ปิดงานแบบไม่พบปัญหา {row.history.false_alarms} ครั้ง —
                        เป็นหลักฐานเรื่องกฎ ไม่ใช่เรื่องเครื่อง
                      </span>
                    </>
                  )}
                </li>
              ))}
            </ol>
          </div>

          <div className="card">
            <h3>มีเรื่องค้างอยู่ตอนนี้</h3>
            <ol className="health-list">
              {health.by_now.map((row) => (
                <li key={`now-${row.machine_id}`}>
                  <strong>{row.machine_id}</strong>{" "}
                  <span className="muted">
                    {row.now.open_findings === 0
                      ? "ไม่มีอะไรค้าง"
                      : `${row.now.open_findings} เรื่อง · หนักสุด ${row.now.highest_severity}`}
                  </span>
                  <br />
                  <span className="muted">{row.now.reason}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>

        {/* Principle 5, where it matters: the caveat belongs next to the number
            a person is deciding from, not in a document they will not open. */}
        <div className="card">
          <h3>สิ่งที่หน้านี้ยังบอกไม่ได้</h3>
          <ul className="muted">
            {health.absent.map((sentence) => (
              <li key={sentence}>{sentence}</li>
            ))}
          </ul>
        </div>

        {health.unplaced_machines.length > 0 && (
          <p className="muted">
            เครื่องที่มีประวัติแต่ไม่อยู่ในผัง:{" "}
            {health.unplaced_machines.join(", ")} — ไม่ได้อยู่ในสองรายการข้างบน
            เพราะผังไม่รู้จัก (ADR-048)
          </p>
        )}
      </section>

      <section>
        <h2>ที่ระบบยังตอบไม่ได้</h2>

        <div className="card">
          <h3>อาการที่ยังไม่มี playbook ({unanswered.no_playbook.count})</h3>
          {drafting !== undefined && (
            <p className="recorded">
              {already === undefined
                ? `ขอร่าง ${drafting} แล้ว — worker-authoring จะดึงไปทำ แล้วไปโผล่ที่คิวรีวิว`
                : already === "review"
                  ? `${drafting} มีร่างรออนุมัติอยู่ที่คิวรีวิวแล้ว — ไม่ได้ขอซ้ำ`
                  : `${drafting} อยู่ในคิวร่างอยู่แล้ว — ใบเดิม ไม่ได้ขอซ้ำ`}
            </p>
          )}
          {unanswered.no_playbook.rows.length === 0 ? (
            <p className="muted">ไม่มี</p>
          ) : (
            <ul className="gaps">
              {unanswered.no_playbook.rows.map((row) => (
                <li key={`${row.symptom_code}-${row.machine_model}`}>
                  <strong>{row.symptom_code}</strong> · {row.machine_model} ·
                  เจอ {row.findings} ครั้ง ({row.occurrences} เหตุการณ์)
                  {row.proposals_waiting > 0 && (
                    <span className="muted">
                      {" "}
                      · มีร่างรออนุมัติ {row.proposals_waiting}
                    </span>
                  )}
                  {/* Engineers only, because the endpoint admits nobody else:
                      the worker behind it holds the one GPU (ADR-029), and a
                      queue anybody can fill is one its owner does not control.
                      Hidden here as well as refused there - a button that
                      always answers 403 is a screen lying about what it does. */}
                  {account.role === "engineer" &&
                    row.proposals_waiting === 0 && (
                      <details>
                        <summary>ขอร่างจากคู่มือ</summary>
                        <form method="post" action="/overview/draft">
                          <input
                            type="hidden"
                            name="symptom_code"
                            value={row.symptom_code}
                          />
                          <input
                            type="hidden"
                            name="machine_model"
                            value={row.machine_model}
                          />
                          <label className="field">
                            <span>ถามคู่มือว่าอะไร</span>
                            <input
                              type="text"
                              name="question"
                              required
                              placeholder="เช่น มอเตอร์สายพานร้อนเกิน 85 องศา"
                            />
                          </label>
                          <button type="submit" className="quiet">
                            ขอร่าง
                          </button>
                        </form>
                      </details>
                    )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <h3>ร่างที่รอวิศวกรรีวิว ({unanswered.awaiting_review.count})</h3>
          {unanswered.awaiting_review.rows.length === 0 ? (
            <p className="muted">ไม่มี</p>
          ) : (
            <ul className="gaps">
              {unanswered.awaiting_review.rows.map((row) => (
                <li key={row.machine_model}>
                  <strong>{row.machine_model}</strong> · {row.waiting} ใบ ·
                  เก่าสุด {plantTime(row.oldest, overview.timezone)}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <h3>
            playbook ที่คู่มือถูกเปลี่ยน ({unanswered.manual_changed.count})
          </h3>
          {unanswered.manual_changed.rows.length === 0 ? (
            <p className="muted">ไม่มี</p>
          ) : (
            <ul className="gaps">
              {unanswered.manual_changed.rows.map((row) => (
                <li key={`${row.symptom_code}-${row.machine_model}`}>
                  <strong>{row.symptom_code}</strong> · {row.machine_model} ·
                  rev {row.revision}
                  {row.review_reason !== null && (
                    <span className="muted"> · {row.review_reason}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </>
  );
}

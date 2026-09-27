import { NotYours, Shell } from "@/app/ui/shell";

import { LineDiagram, LineFaults } from "@/app/overview/line-diagram";
import { SEVERITY, plantDateTime, plantTime } from "@/lib/display";
import { lineOverview, machineHealth } from "@/lib/overview";
import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";

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
export default async function OverviewPage() {
  const account = await requireAccount();
  if (account.role !== "supervisor" && account.role !== "engineer") {
    return (
      <Shell account={account} current="/overview">
        <NotYours home={homeFor(account.role)} what="หน้านี้เป็นของหัวหน้ากะและวิศวกร" />
      </Shell>
    );
  }

  const [overview, health] = await Promise.all([lineOverview(), machineHealth()]);
  const shift = overview.shift;
  const load = shift.load_ratio === null ? null : Math.round(shift.load_ratio * 100);

  return (
    <Shell account={account} current="/overview">
      <div className="who">
        <h1 style={{ margin: 0 }}>สายการผลิต</h1>
        <span className="muted">อัปเดต {plantTime(overview.at, overview.timezone)} น.</span>
      </div>

      <div className="stats">
        <div className="stat">
          <div className="label">ภาระงานของกะ</div>
          <div className="big-number">{load === null ? "—" : `${load}%`}</div>
          <div className={`meter ${shift.band}`}>
            <span style={{ width: `${Math.min(load ?? 0, 100)}%` }} />
          </div>
        </div>
        <div className="stat">
          <div className="label">ช่างในกะ</div>
          <div className="big-number">{shift.technicians_on_shift}</div>
        </div>
        <div className="stat">
          <div className="label">งานเปิดอยู่</div>
          <div className="big-number">{shift.open_orders}</div>
        </div>
      </div>
      <p className="muted">
        {shift.summary} · ใช้ไป {shift.committed_minutes} จาก {shift.capacity_minutes} นาที-คน
      </p>

      {overview.lines.map((line) => (
        <section key={line.line_id}>
          <h2>ผังสาย {line.line_id}</h2>
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
                      : `${row.now.open_findings} เรื่อง · หนักสุดระดับ${SEVERITY[row.now.highest_severity ?? ""] ?? "-"}`}
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
            เพราะผังไม่รู้จัก
          </p>
        )}
      </section>

    </Shell>
  );
}

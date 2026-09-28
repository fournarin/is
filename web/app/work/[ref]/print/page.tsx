import { Shell } from "@/app/ui/shell";
import { bandFor, minutesText } from "@/lib/display";
import { requireAccount } from "@/lib/session";
import { ticket } from "@/lib/work";

/**
 * The work order on one sheet of paper. The plant still runs on paper, and a
 * printout is the bridge from it (ADR-093). Same fields as the screen, nothing
 * composed here.
 */
export default async function PrintPage({ params }: { params: Promise<{ ref: string }> }) {
  const account = await requireAccount();
  const { ref } = await params;
  const job = await ticket(decodeURIComponent(ref));
  const band = bandFor(job);

  return (
    <Shell account={account} current="/work">
      <p className="no-print recorded">🖨️ กด Ctrl+P (หรือเมนู &quot;พิมพ์&quot; ของเบราว์เซอร์) เพื่อพิมพ์ใบงานนี้</p>
      <section className="card">
        <div className="job-head">
          <h1 style={{ margin: 0 }}>ใบงานซ่อม {job.ref}</h1>
          <span className={`pill ${band.tone}`}>{band.label}</span>
        </div>
        <p className="machine">
          {job.machine_id}
          {job.station !== null && ` · ${job.station}`}
        </p>
        <p className="symptom">{job.reason}</p>
        <div className="facts">
          <div className="fact">
            <span className="label">เวลาโดยประมาณ</span>
            <span className="value">{minutesText(job.estimated_minutes)}</span>
          </div>
          <div className="fact">
            <span className="label">ทักษะที่ใช้</span>
            <span className="value">{job.required_skill_name ?? "ทั่วไป"}</span>
          </div>
          <div className="fact">
            <span className="label">จำนวนช่าง</span>
            <span className="value">{job.required_technicians} คน</span>
          </div>
        </div>
        {job.tools.length > 0 && (
          <p>
            <strong>เครื่องมือ:</strong> {job.tools.join(" · ")}
          </p>
        )}
        {job.priority_reason !== "" && (
          <div className="why">
            <span className="label">ทำไมต้องทำงานนี้ก่อน</span>
            <p className="reason">{job.priority_reason}</p>
          </div>
        )}
        <h2>ขั้นตอนซ่อม</h2>
        {job.steps.length === 0 ? (
          <p>ยังไม่มีขั้นตอนที่อนุมัติแล้ว ให้ดูคู่มือของเครื่องหรือถามวิศวกร</p>
        ) : (
          <ol className="checklist">
            {job.steps.map((one, index) => (
              <li key={index}>
                <span>
                  ☐ {one.text_th ?? one.text}{" "}
                  <span className="muted">
                    ({one.manual ?? "คู่มือ"} หน้า {one.page}
                    {one.text_th !== null && <>: <span lang="en">{one.text}</span></>})
                  </span>
                </span>
              </li>
            ))}
          </ol>
        )}
        <h2>บันทึกของช่าง</h2>
        <p>ผู้ทำ ____________________ เริ่ม ______ เสร็จ ______ ผล ☐ ซ่อมแล้ว ☐ ไม่พบปัญหา ☐ ส่งต่อ</p>
      </section>
    </Shell>
  );
}

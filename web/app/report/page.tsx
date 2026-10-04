import { Shell } from "@/app/ui/shell";

import { ReportForm } from "@/app/report/report-form";
import { KeepFresh } from "@/app/ui/keep-fresh";
import { machines, myReports } from "@/lib/report";
import { requireAccount } from "@/lib/session";

/**
 * Reporting a fault, for whoever is standing there (ADR-077 §1).
 *
 * No role check on this page, deliberately, and that is not the same as no
 * check: the API refuses an anonymous report and records every one that is made
 * (invariant 6). All four roles may report, and the operator - who has been
 * offered nothing by this shell since it was built - is the one most likely to
 * be next to the machine when it starts making a noise.
 */
export default async function ReportPage() {
  const account = await requireAccount();
  const [floor, mine] = await Promise.all([machines(), myReports()]);

  return (
    <Shell account={account} current="/report">
      <h1>📣 แจ้งซ่อม</h1>
      <p className="muted">
        เลือกเครื่อง บอกสิ่งที่เห็นหรือได้ยิน ไม่ต้องวินิจฉัยเอง ระบบจะเปิดใบงานให้ แล้วหัวหน้ากะยืนยันก่อนส่งถึงช่าง
      </p>
      <ReportForm machines={floor} />

      {/* What happened to each report, so it can be found again after it was
          sent (ADR-122). In the owner's second trial it could not. */}
      <KeepFresh />
      <h2>เรื่องที่คุณแจ้งไว้</h2>
      {mine.length === 0 ? (
        <p className="muted">ยังไม่เคยแจ้ง</p>
      ) : (
        mine.map((one) => (
          <article className="ticket" key={one.ref}>
            <div className="ticket-head">
              <span className="machine-small">{one.machine_id}</span>
              <span className={`pill ${one.finished ? "done" : ""}`}>{one.where}</span>
            </div>
            {/* What they wrote: two reports on one machine looked identical
                without it (fourth trial, finding 19). */}
            {one.what && <p>“{one.what}”</p>}
            <p className="muted">
              {one.ref} · แจ้งเมื่อ {one.reported_when}
            </p>
          </article>
        ))
      )}
    </Shell>
  );
}

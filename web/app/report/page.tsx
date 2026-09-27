import { Shell } from "@/app/ui/shell";

import { ReportForm } from "@/app/report/report-form";
import { machines } from "@/lib/report";
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
  const floor = await machines();

  return (
    <Shell account={account} current="/report">
      <h1>📣 แจ้งซ่อม</h1>
      <p className="muted">
        เลือกเครื่อง บอกสิ่งที่เห็นหรือได้ยิน ไม่ต้องวินิจฉัยเอง ระบบจะเปิดใบงานให้ แล้วหัวหน้ากะยืนยันก่อนส่งถึงช่าง
      </p>
      <ReportForm machines={floor} />
    </Shell>
  );
}

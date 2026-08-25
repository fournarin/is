import Link from "next/link";

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
  await requireAccount();
  const floor = await machines();

  return (
    <>
      <div className="who">
        <span>แจ้งงานเสีย</span>
        <Link href="/">หน้าแรก</Link>
      </div>
      <h1>เจออะไรผิดปกติ</h1>
      <p className="muted">
        แจ้งสิ่งที่เห็น ไม่ต้องวินิจฉัย ระบบจะเปิดใบงานจากคำที่คุณเขียน แล้วให้หัวหน้ากะยืนยันก่อนจ่ายงาน
      </p>
      <ReportForm machines={floor} />
    </>
  );
}

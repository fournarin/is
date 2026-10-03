import { NotYours, Shell } from "@/app/ui/shell";
import { plantDateTime } from "@/lib/display";
import { bySymptom } from "@/lib/notes";
import { floorNotes } from "@/lib/notes-api";
import { homeFor } from "@/lib/screens";
import { ROLE_NAMES, requireAccount } from "@/lib/session";

const OUTCOME: Readonly<Record<string, string>> = {
  fixed: "แก้แล้ว",
  temporary_fix: "แก้ชั่วคราว",
  not_fixed: "ยังไม่หาย",
  no_problem_found: "ไม่พบปัญหา",
};

/**
 * What the technicians wrote when they closed a job (ADR-117).
 *
 * The note on the close screen was stored and read by nothing, so "step 3 needs
 * a 13 mm socket" reached nobody. Here it reaches the engineer who owns the
 * steps, grouped by the symptom it is about, newest first. There is no button:
 * a note that should become a step goes through the review queue, which records
 * who approved it (ADR-064).
 */
export default async function NotesPage() {
  const account = await requireAccount();
  if (account.role !== "engineer" && account.role !== "supervisor") {
    return (
      <Shell account={account} current="/notes">
        <NotYours home={homeFor(account.role)} what="หน้านี้เป็นของวิศวกรและหัวหน้ากะ" />
      </Shell>
    );
  }

  const { timezone, notes } = await floorNotes();
  const groups = bySymptom(notes);

  return (
    <Shell account={account} current="/notes">
      <div className="who">
        <span>
          บันทึกจากช่างตอนปิดงาน
          <span className="muted"> · {ROLE_NAMES[account.role]}</span>
        </span>
      </div>

      <p className="muted">
        ข้อความที่ช่างพิมพ์ไว้ตอนปิดงาน เรียงจากล่าสุด แยกตามอาการ ถ้าควรแก้ขั้นตอนซ่อม
        ให้แก้ผ่านการอนุมัติขั้นตอน ซึ่งบันทึกว่าใครอนุมัติ
      </p>

      {groups.length === 0 ? (
        <p className="card">ยังไม่มีช่างเขียนบันทึกตอนปิดงาน</p>
      ) : (
        groups.map(([symptom, list]) => (
          <article className="card" key={symptom}>
            <h2>
              {list[0]?.symptom_title ?? symptom}{" "}
              <span className="muted">
                · {list[0]?.symptom_title ? `${symptom} · ` : ""}
                {list.length} บันทึก
              </span>
            </h2>
            <ul>
              {list.map((one) => (
                <li key={one.work_order_ref}>
                  <p>“{one.note}”</p>
                  <p className="muted">
                    {one.machine_id} · ใบงาน {one.work_order_ref} ·{" "}
                    {one.outcome ? (OUTCOME[one.outcome] ?? one.outcome) : "ไม่ระบุผล"} · ปิดเมื่อ{" "}
                    {plantDateTime(one.closed_at, timezone)}
                  </p>
                </li>
              ))}
            </ul>
          </article>
        ))
      )}
    </Shell>
  );
}

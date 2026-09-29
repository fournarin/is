/**
 * Which tabs each role is offered, and where each role lands.
 *
 * ADR-024's table is the authority on who may do what; this list only decides
 * what a person is shown. Each role lands on its own work rather than on a menu
 * of screens (ADR-093): a technician opens the app to a job, a shift lead to
 * the board, an engineer to what is waiting for sign-off.
 */
import type { Role } from "@/lib/session";

export type Tab = {
  href: string;
  label: string;
  icon: string;
};

const WORK: Tab = { href: "/work", label: "งานของฉัน", icon: "🔧" };
const REPORT: Tab = { href: "/report", label: "แจ้งซ่อม", icon: "📣" };
const BOARD: Tab = { href: "/board", label: "กระดานงาน", icon: "📋" };
const LINE: Tab = { href: "/overview", label: "สายการผลิต", icon: "🏭" };
const REVIEW: Tab = { href: "/review", label: "อนุมัติขั้นตอน", icon: "✅" };
const GAPS: Tab = { href: "/gaps", label: "ยังไม่มีขั้นตอน", icon: "📚" };
const LOOPS: Tab = { href: "/loops", label: "ข้อเสนอปรับค่า", icon: "📈" };
const NOTES: Tab = { href: "/notes", label: "บันทึกจากช่าง", icon: "📝" };

export const TABS: Readonly<Record<Role, readonly Tab[]>> = {
  technician: [WORK, REPORT],
  supervisor: [BOARD, LINE, REPORT],
  engineer: [REVIEW, GAPS, LINE, LOOPS, NOTES],
  operator: [REPORT],
};

export function tabsFor(role: Role): readonly Tab[] {
  return TABS[role];
}

/** Where a role goes when it signs in or opens the app. */
export function homeFor(role: Role): string {
  return TABS[role][0]!.href;
}

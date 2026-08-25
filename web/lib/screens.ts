/**
 * What the shell offers, and to whom.
 *
 * ADR-024's table is the authority on who may do what; this list only decides
 * what a person is offered. Every screen here is still unbuilt, and each says
 * which slice builds it: principle 5 - when the evidence is thin, say so -
 * applies to the system describing itself as much as it does to a playbook.
 */
import type { Role } from "@/lib/session";

export type Screen = {
  title: string;
  purpose: string;
  /** The backlog slice that builds it. Shown on screen while `href` is null. */
  slice: string;
  /** Where it lives, once it exists. Null means the slice has not landed. */
  href: string | null;
  roles: readonly Role[];
};

export const SCREENS: readonly Screen[] = [
  {
    title: "คิวรีวิว playbook",
    purpose: "อนุมัติขั้นตอนซ่อมทีละใบ โดยมีหลักฐานจากคู่มืออยู่ข้างกันในจอเดียว",
    slice: "10.2",
    href: "/review",
    // The supervisor is offered it because the API lets them read it: a
    // supervisor who cannot see the queue cannot ask why it is not moving.
    // Approving is still an engineer's alone, refused at the endpoint rather
    // than by this list (invariant 6, ADR-024).
    roles: ["engineer", "supervisor"],
  },
  {
    title: "งานของคุณ",
    purpose: "ใบงานที่ระบบจัดให้ เหตุผลว่าทำไมใบนี้ก่อน ขั้นตอนซ่อม และการปิดงาน",
    slice: "10.3-10.4",
    href: "/work",
    roles: ["technician"],
  },
  {
    title: "แจ้งงานเสีย",
    purpose: "บอกระบบเรื่องที่กฎยังจับไม่ได้ จากคนที่ยืนอยู่หน้าเครื่อง",
    slice: "16.2",
    href: "/report",
    // Every role, and the only screen an operator is offered at all: whoever is
    // standing there is who sees it, and nothing is dispatched on a report alone
    // (ADR-077 §1, ADR-071).
    roles: ["technician", "engineer", "supervisor", "operator"],
  },
  {
    title: "ภาพรวมสายการผลิต",
    purpose: "สถานีไหนกำลังจะถึงเกณฑ์ กะนี้รับไหวแค่ไหน และใบงานที่ประตูโหลดกั้นไว้",
    slice: "10.5",
    href: "/overview",
    roles: ["supervisor", "engineer"],
  },
];

export function screensFor(role: Role): readonly Screen[] {
  return SCREENS.filter((screen) => screen.roles.includes(role));
}

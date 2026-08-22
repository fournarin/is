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
    href: null,
    roles: ["engineer"],
  },
  {
    title: "งานของคุณ",
    purpose: "ใบงานที่ระบบจัดให้ เหตุผลว่าทำไมใบนี้ก่อน ขั้นตอนซ่อม และการปิดงาน",
    slice: "10.3-10.4",
    href: "/work",
    roles: ["technician"],
  },
  {
    title: "ภาพรวมสายการผลิต",
    purpose: "สถานีไหนกำลังจะถึงเกณฑ์ กะนี้รับไหวแค่ไหน และใบงานที่ประตูโหลดกั้นไว้",
    slice: "10.5",
    href: null,
    roles: ["supervisor", "engineer"],
  },
];

export function screensFor(role: Role): readonly Screen[] {
  return SCREENS.filter((screen) => screen.roles.includes(role));
}

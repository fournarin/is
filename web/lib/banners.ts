/**
 * What the board says after a press, naming the job the way the floor does.
 *
 * "ยืนยัน WO-000011 แล้ว" told the shift lead nothing they could check against
 * the card they had just pressed (fourth trial, finding 8). The title is the
 * backend's - machine and symptom - and the ticket number stands in only when
 * the ticket could not be read. No glyphs: the screen puts its own icon beside
 * it (design system, ADR-141). No imports, so `node --test` can run it.
 */
export type Pressed = "confirmed" | "rejected" | "brought" | "released";

export function bannerFor(
  pressed: Pressed,
  ref: string,
  title: string | null | undefined,
  names: string[] = [],
): string {
  // Thai joins "ยืนยัน" and "งาน" with no space; a bare reference needs one.
  const job = title ? `งาน ${title}` : ` ${ref}`;
  switch (pressed) {
    case "confirmed":
      return names.length > 0
        ? `ยืนยัน${job} แล้ว ส่งถึง ${names.join(", ")} แล้ว`
        : `ยืนยัน${job} แล้ว งานถูกส่งถึงช่างแล้ว`;
    case "rejected":
      return `พัก${job} ไว้แล้ว ระบบจะไม่เสนองานนี้อีกในกะนี้ จนกว่าคุณจะกด “นำกลับมา”`;
    case "brought":
      return `นำ${job} กลับมาแล้ว ระบบจะเลือกช่างให้ในรอบถัดไป (ไม่เกิน 5 นาที)`;
    case "released":
      return `ปล่อย${job} แล้ว ระบบจะเลือกช่างให้ในรอบถัดไป (ไม่เกิน 5 นาที)`;
  }
}

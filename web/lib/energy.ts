/**
 * What a marked step still needs from the reader before the job moves past it
 * (ADR-135, ADR-136).
 *
 * The same rule `pdm.work.locks.still_needed` enforces on the server, mirrored
 * here only to draw the tiles and the button and to say what is left: the API
 * refuses either way. Per person - your own lock on now, your own verify - and
 * read from the marks the approving engineer set, never from the words of a
 * step (REQ-H-02).
 */
import type { LockOn, PointConfirmed, Step } from "@/lib/work";

export type Needed = { point_id: string; item: string };

export type Who = { user: string; locksOn: readonly LockOn[]; checks: readonly string[] };

/** When a waiting step may be left, or null if its clock has not started. */
export function waitEnds(step: Step, number: number, done: readonly PointConfirmed[]): Date | null {
  if (!step.wait_minutes) return null;
  const started = done.find((one) => one.step === number && one.item === "wait_started");
  return started ? new Date(Date.parse(started.at) + step.wait_minutes * 60_000) : null;
}

/** Points whose restore step comes before `before` (1-based): their locks may be off. */
export function restoredBefore(steps: readonly Step[], before: number): Set<string> {
  const points = new Set<string>();
  steps.slice(0, Math.max(0, before - 1)).forEach((step) => {
    if (step.kind === "restore") (step.isolation_points ?? []).forEach((point) => points.add(point.point_id));
  });
  return points;
}

export function stillNeeded(
  step: Step,
  number: number,
  done: readonly PointConfirmed[],
  now: Date,
  who: Who,
  restored: Set<string> = new Set(),
): Needed[] {
  const here = done.filter((one) => one.step === number);
  const byAnybody = new Set(here.map((one) => `${one.point_id}|${one.item}`));
  const byYou = new Set(here.filter((one) => one.by === who.user).map((one) => `${one.point_id}|${one.item}`));
  const yoursOn = new Set(who.locksOn.filter((one) => one.owner === who.user).map((one) => one.point_id));
  const anyOn = new Set(who.locksOn.map((one) => one.point_id));
  const points = (step.isolation_points ?? []).map((point) => point.point_id);
  const needed: Needed[] = [];
  if (step.kind === "isolation") {
    for (const point of points) {
      if (!byAnybody.has(`${point}|off`)) needed.push({ point_id: point, item: "off" });
      if (!yoursOn.has(point) && !restored.has(point)) needed.push({ point_id: point, item: "locked" });
    }
  } else if (step.kind === "verify") {
    points.filter((point) => !byYou.has(`${point}|verified`)).forEach((point) => needed.push({ point_id: point, item: "verified" }));
  } else if (step.kind === "restore") {
    who.checks.filter((key) => !byAnybody.has(`${key}|checked`)).forEach((key) => needed.push({ point_id: key, item: "checked" }));
    points.filter((point) => anyOn.has(point)).forEach((point) => needed.push({ point_id: point, item: "released" }));
  }
  if (step.wait_minutes) {
    const ends = waitEnds(step, number, done);
    if (ends === null || now < ends) needed.push({ point_id: "", item: "wait_started" });
  }
  return needed;
}

/** The first step before `before` (1-based) that still needs something - the API's own gate. */
export function firstUnfinished(
  steps: readonly Step[],
  done: readonly PointConfirmed[],
  before: number,
  now: Date,
  who: Who,
): { number: number; missing: Needed[] } | null {
  const restored = restoredBefore(steps, before);
  for (let number = 1; number < before && number <= steps.length; number += 1) {
    const missing = stillNeeded(steps[number - 1]!, number, done, now, who, restored);
    if (missing.length > 0) return { number, missing };
  }
  return null;
}

/** How each confirmation is said in "ยังต้องยืนยัน: ...". */
export const SAID: Readonly<Record<string, string>> = {
  off: "ตัดพลังงาน",
  locked: "ใส่กุญแจของคุณ",
  verified: "ตรวจพลังงานเป็นศูนย์",
  checked: "ตรวจก่อนจ่ายไฟ",
  released: "ปลดกุญแจ",
  wait_started: "รอให้ครบเวลา",
};

/**
 * The sticky link's words on an energy step: what to do next and where, never the step's own name again
 * (w1 check note 4: a verify step read "ต่อไป: ตรวจพลังงานเป็นศูนย์" under the heading that says the same).
 */
export function nextLine(missing: readonly Needed[]): string {
  const first = missing.find((one) => one.item !== "wait_started");
  if (first === undefined) return "ต่อไป: รอให้ครบเวลา";
  if (first.item === "verified") {
    const where = [...new Set(missing.filter((one) => one.item === "verified").map((one) => one.point_id))];
    return `ต่อไป: วัดที่ ${where.join(" / ")}`;
  }
  if (first.item === "checked") return `ต่อไป: ${SAID.checked}`;
  return `ต่อไป: ${SAID[first.item] ?? first.item} ที่ ${first.point_id}`;
}

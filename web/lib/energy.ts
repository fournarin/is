/**
 * What a marked step still needs before the job moves past it (ADR-135).
 *
 * The same rule `pdm.work.locks.still_needed` enforces on the server, mirrored
 * here only to draw the button and say what is left: the API refuses either
 * way. Read from the marks the approving engineer set, never from the words of
 * a step (REQ-H-02).
 */
import type { PointConfirmed, Step } from "@/lib/work";

export const ITEMS: Readonly<Record<string, readonly string[]>> = {
  isolation: ["off", "locked"],
  verify: ["verified"],
  restore: ["released"],
};

export type Needed = { point_id: string; item: string };

/** When a waiting step may be left, or null if its clock has not started. */
export function waitEnds(step: Step, number: number, done: readonly PointConfirmed[]): Date | null {
  if (!step.wait_minutes) return null;
  const started = done.find((one) => one.step === number && one.item === "wait_started");
  return started ? new Date(Date.parse(started.at) + step.wait_minutes * 60_000) : null;
}

export function stillNeeded(step: Step, number: number, done: readonly PointConfirmed[], now: Date): Needed[] {
  const have = new Set(done.filter((one) => one.step === number).map((one) => `${one.point_id}|${one.item}`));
  const needed: Needed[] = [];
  for (const point of step.isolation_points ?? []) {
    for (const item of ITEMS[step.kind ?? "normal"] ?? []) {
      if (!have.has(`${point.point_id}|${item}`)) needed.push({ point_id: point.point_id, item });
    }
  }
  if (step.wait_minutes) {
    const ends = waitEnds(step, number, done);
    if (ends === null || now < ends) needed.push({ point_id: "", item: "wait_started" });
  }
  return needed;
}

/** How each confirmation is said in "ยังต้องยืนยัน: ...". */
export const SAID: Readonly<Record<string, string>> = {
  off: "ตัดพลังงาน",
  locked: "ใส่กุญแจ",
  verified: "ตรวจพลังงานเป็นศูนย์",
  released: "ปลดกุญแจ",
  wait_started: "รอให้ครบเวลา",
};

/** The first step before `before` (1-based) that still needs something - the API's own gate. */
export function firstUnfinished(
  steps: readonly Step[],
  done: readonly PointConfirmed[],
  before: number,
  now: Date,
): { number: number; missing: Needed[] } | null {
  for (let number = 1; number < before && number <= steps.length; number += 1) {
    const missing = stillNeeded(steps[number - 1]!, number, done, now);
    if (missing.length > 0) return { number, missing };
  }
  return null;
}

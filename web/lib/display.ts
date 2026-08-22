/**
 * Turning what the API said into what a person reads, and nothing more.
 *
 * No sentence is composed here. `reason` and `priority_reason` arrive written
 * (ADR-005), and this file only decides what colour a band is and how a
 * timestamp is spelled.
 */
import type { Ticket } from "@/lib/work";

/**
 * Plant-local, always.
 *
 * The zone comes from the round, which reads it from `config/plant.yaml`, never
 * from the device: a shift lead reading this from a laptop set to UTC still has
 * to see the shift's own clock.
 */
export function plantTime(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("th-TH", {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function plantDateTime(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("th-TH", {
    timeZone: timezone,
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export type Band = { label: string; tone: "urgent" | "planned" | "normal" | "low" };

/**
 * A predicted job is never dressed as an urgent one, whatever its severity.
 *
 * ADR-020: a technician decides differently about a machine that is already
 * wrong and one that is not yet. Shown alike they will run at both, and stop
 * trusting the system the first time they arrive at a healthy machine - so
 * `finding_kind` is checked before severity, not after.
 */
export function bandFor(one: Ticket): Band {
  if (one.finding_kind === "predicted") {
    return { label: "วางแผนไว้", tone: "planned" };
  }
  if (one.severity === "critical" || one.severity === "high") {
    return { label: "ด่วน", tone: "urgent" };
  }
  if (one.severity === "medium") {
    return { label: "ปกติ", tone: "normal" };
  }
  return { label: "ไม่เร่ง", tone: "low" };
}

/** "เห็นมาแล้ว 34 ครั้ง ตั้งแต่ 08:12", or null when there is nothing to count. */
export function seenLine(one: Ticket, timezone: string): string | null {
  if (one.recurrence === null) {
    return null;
  }
  const since = plantTime(one.recurrence.detected_at, timezone);
  return `เห็นมาแล้ว ${one.recurrence.occurrence_count} ครั้ง ตั้งแต่ ${since}`;
}

/**
 * What a close is, and how to read one out of a form.
 *
 * Shared by the route handler and the client component, so the two cannot
 * drift into sending different things - and therefore **pure**. Nothing here
 * may import `lib/api.ts`: that reaches for `next/headers`, and a shared module
 * that touches it drags the server into the browser bundle and fails the build
 * with a stack naming this file rather than the import that did it. `sendClose`
 * lives in the route handler for that reason.
 */

export const OUTCOMES = ["fixed", "temporary_fix", "not_fixed", "no_problem_found"] as const;
export const BLOCKED_REASONS = ["waiting_parts", "waiting_line_stop", "waiting_help"] as const;

export type Outcome = (typeof OUTCOMES)[number];
export type BlockedReason = (typeof BLOCKED_REASONS)[number];

export const LOCK_STATES = ["released", "released_machine_locked", "still_locked", "not_isolated"] as const;
export type LockState = (typeof LOCK_STATES)[number];

export type ClosePayload = {
  outcome: Outcome;
  blocked_reason: BlockedReason[];
  blocked_minutes: number;
  technician_feedback: string | null;
  // Checked by the API against the lock register (REQ-H-06, ADR-135).
  lock_state?: LockState;
  lock_reason?: string | null;
};

export function isLockState(value: string): value is LockState {
  return (LOCK_STATES as readonly string[]).includes(value);
}

/** The lock answer out of a form or a JSON body; nothing when it was not given. */
export function lockAnswer(state: unknown, reason: unknown): Pick<ClosePayload, "lock_state" | "lock_reason"> {
  const answer = String(state ?? "");
  if (!isLockState(answer)) return {};
  const why = String(reason ?? "").trim();
  return { lock_state: answer, lock_reason: answer === "still_locked" && why !== "" ? why : null };
}

export function isOutcome(value: string): value is Outcome {
  return (OUTCOMES as readonly string[]).includes(value);
}

export function isBlockedReason(value: string): value is BlockedReason {
  return (BLOCKED_REASONS as readonly string[]).includes(value);
}

/**
 * Read a close out of a submitted form.
 *
 * **No field asks for a duration** and none is read here. `actual_minutes` is
 * the sum of the segments "start" and "hand over" opened (ADR-025); asking a
 * technician for a number at the end of a shift buys a guess, and the guesses
 * destroy the loop ADR-006 is built on. `blocked_minutes` is the opposite kind
 * of number - time that was *not* repair - and it is subtracted rather than
 * counted.
 */
export function closeFromForm(form: FormData): ClosePayload | null {
  const outcome = String(form.get("outcome") ?? "");
  if (!isOutcome(outcome)) {
    return null;
  }
  const reasons = form.getAll("blocked_reason").map(String).filter(isBlockedReason);
  const minutes = Number(form.get("blocked_minutes") ?? 0);
  const note = String(form.get("technician_feedback") ?? "").trim();
  return {
    outcome,
    blocked_reason: reasons,
    // Minutes only mean something beside a reason. A number with no chip is a
    // stray keystroke, and subtracting it would quietly shorten the job.
    blocked_minutes: reasons.length === 0 || !Number.isFinite(minutes) ? 0 : Math.max(0, minutes),
    technician_feedback: note === "" ? null : note,
    ...lockAnswer(form.get("lock_state"), form.get("lock_reason")),
  };
}

/**
 * A status that means nothing behind this server answered: the close was not
 * refused, it was never read. The phone keeps it and sends it later, as it does
 * when its own network drops. A 500 is not one of these - that is the API
 * answering with a fault, and retrying it for ever would never drain the queue.
 */
export function reachedNobody(status: number): boolean {
  return status === 502 || status === 503 || status === 504;
}

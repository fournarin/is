"use server";

import { redirect } from "next/navigation";

import { callApi } from "@/lib/api";

/**
 * Take the job and open a segment, in that order.
 *
 * One button, two calls. `accept` is idempotent for somebody who already holds
 * the order - a round that placed it has already written them in - and `start`
 * refuses anybody who does not, so calling both is one code path rather than a
 * branch on what a previous round happened to do. The technician presses one
 * thing, which is what a phone at a machine deserves.
 */
async function reason(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // not JSON
  }
  return `ระบบตอบกลับผิดปกติ (${response.status}) ลองโหลดหน้าใหม่`;
}

export async function startWork(ref: string): Promise<void> {
  const accepted = await callApi(`/work-orders/${encodeURIComponent(ref)}/accept`, {
    method: "POST",
  });
  if (!accepted.ok) {
    // Back to the job with the API's own sentence, never a crash page: a
    // double tap or a stale page is normal on a phone (ADR-102).
    redirect(`/work?error=${encodeURIComponent(await reason(accepted))}`);
  }
  const started = await callApi(`/work-orders/${encodeURIComponent(ref)}/start`, {
    method: "POST",
  });
  // 409 is "already working on it": the second tap of the same button.
  if (!started.ok && started.status !== 409) {
    redirect(`/work?error=${encodeURIComponent(await reason(started))}`);
  }
  redirect(`/work/${encodeURIComponent(ref)}/steps`);
}

export type HandoverState = { error: string | null };

/**
 * Put the job down for somebody else, and say how far it got.
 *
 * The work order arrives as a hidden field rather than through `.bind()`, and
 * that is not a style choice. A bound action that **returns state** instead of
 * redirecting never finishes its response on the no-JavaScript path - the
 * request hangs, and the phone this is built for is exactly the one whose
 * bundle did not arrive. `startWork` above may stay bound because it always
 * redirects. Nothing catches this but running the page: see
 * `check-the-technicians-screen.py`.
 *
 * A hidden field can be edited, and it does not need to be trusted: the API
 * refuses a handover from somebody who does not hold the order.
 *
 * The note is not optional and the API refuses an empty one. It is checked here
 * as well so that the button cannot be pressed into a round trip that was
 * always going to fail - ADR-025 wants the note because without it the next
 * shift finds an open order and starts from step one.
 */
export async function handOver(
  _previous: HandoverState,
  form: FormData,
): Promise<HandoverState> {
  const ref = String(form.get("ref") ?? "");
  const note = String(form.get("note") ?? "").trim();
  if (note === "") {
    return { error: "เขียนสั้น ๆ ว่าทำถึงไหนแล้ว ก่อนส่งต่องาน" };
  }

  const response = await callApi(`/work-orders/${encodeURIComponent(ref)}/handover`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (response.status === 409) {
    return { error: "งานนี้ถูกเปลี่ยนสถานะไปแล้ว ลองโหลดหน้าใหม่" };
  }
  if (!response.ok) {
    return { error: `ระบบตอบกลับผิดปกติ (${response.status})` };
  }

  redirect(`/work?done=handed&ref=${encodeURIComponent(ref)}`);
}

export type ObjectionState = { error: string | null; recordedAt: string | null };

/**
 * "I disagree" - recorded, and the queue does not move.
 *
 * That is the whole design (ADR-005, ADR-059): a ranking that can be argued
 * down is not a ranking, and what the button is worth is the record. So this
 * returns what was written rather than a message hoping it was, and the screen
 * says plainly that nothing reordered - a button that looked like it changed
 * something and did not is worse than no button.
 *
 * Unbound, and the ref comes through the form, for the reason `handOver` above
 * gives: this one returns state rather than redirecting.
 */
export async function disagree(
  _previous: ObjectionState,
  form: FormData,
): Promise<ObjectionState> {
  const ref = String(form.get("ref") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  if (reason === "") {
    return { error: "เขียนสั้น ๆ ว่าทำไมไม่เห็นด้วย", recordedAt: null };
  }

  const response = await callApi(`/work-orders/${encodeURIComponent(ref)}/disagreement`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) {
    return { error: `ระบบตอบกลับผิดปกติ (${response.status})`, recordedAt: null };
  }

  const recorded = (await response.json()) as { at: string };
  return { error: null, recordedAt: recorded.at };
}

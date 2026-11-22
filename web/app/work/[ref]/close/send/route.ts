/**
 * Where a close is sent, by both paths.
 *
 * A plain HTML form posts here, so closing works on a phone whose JavaScript
 * never arrived - no server action, no bundle, just a form. When JavaScript
 * *is* there the same route takes JSON, because only a client-side `fetch` can
 * tell "the network dropped" from "the API refused": the first is queued on the
 * device and retried, the second is shown. Retrying a refusal for ever is how a
 * queue stops draining and a screen says "not sent yet" until somebody clears
 * the browser.
 */
import type { NextRequest } from "next/server";

import { ApiUnreachable, UNREACHABLE, callApi } from "@/lib/api";
import { type ClosePayload, closeFromForm, isBlockedReason, isOutcome, lockAnswer } from "@/lib/close";
import { seeOther } from "@/lib/redirect";

async function sendClose(ref: string, close: ClosePayload): Promise<Response> {
  return callApi(`/work-orders/${encodeURIComponent(ref)}/close`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(close),
  });
}

function fromJson(body: unknown): ClosePayload | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const one = body as Record<string, unknown>;
  const outcome = String(one.outcome ?? "");
  if (!isOutcome(outcome)) {
    return null;
  }
  const reasons = Array.isArray(one.blocked_reason)
    ? one.blocked_reason.map(String).filter(isBlockedReason)
    : [];
  const minutes = Number(one.blocked_minutes ?? 0);
  const note = typeof one.technician_feedback === "string" ? one.technician_feedback.trim() : "";
  return {
    outcome,
    blocked_reason: reasons,
    blocked_minutes: reasons.length === 0 || !Number.isFinite(minutes) ? 0 : Math.max(0, minutes),
    technician_feedback: note === "" ? null : note,
    ...lockAnswer(one.lock_state, one.lock_reason),
  };
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ ref: string }> },
): Promise<Response> {
  const { ref: encoded } = await context.params;
  const ref = decodeURIComponent(encoded);
  const wantsJson = (request.headers.get("content-type") ?? "").includes("application/json");

  const back = (message: string, status: number): Response =>
    wantsJson
      ? Response.json({ error: message }, { status })
      : seeOther(`/work/${encoded}/close?error=${encodeURIComponent(message)}`);

  const close = wantsJson ? fromJson(await request.json()) : closeFromForm(await request.formData());
  if (close === null) {
    return back("เลือกก่อนว่างานจบอย่างไร", 400);
  }

  let response: Response;
  try {
    response = await sendClose(ref, close);
  } catch (error) {
    if (!(error instanceof ApiUnreachable)) {
      throw error;
    }
    // Not a refusal: nothing answered. 503 is what the phone's queue reads as
    // "keep it and send it later", the same as its own network dropping. As a
    // 500 it was shown as an error and the close was thrown away (2026-09-29).
    return back(`${UNREACHABLE} การปิดงานนี้ยังไม่ถูกส่ง ลองอีกครั้งเมื่อระบบกลับมา`, 503);
  }
  if (!response.ok) {
    // The API's own sentence, not the status code. It is the one that says what
    // to change - "waiting cannot be longer than the work it interrupted" is
    // actionable and "422" is not, and somebody is reading this at a machine.
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    const detail = typeof body.detail === "string" ? body.detail : `ระบบตอบกลับ ${response.status}`;
    return back(detail, response.status);
  }

  return wantsJson ? new Response(null, { status: 204 }) : seeOther(`/work?done=closed&ref=${encoded}`);
}

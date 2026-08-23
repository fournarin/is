/**
 * The press the advisor asked for: this job goes out, to these people, now.
 *
 * A plain HTML form, posted and redirected, for the reason the release route
 * gives: confirming takes the proposal out of the list, so the component that
 * submitted no longer exists when the page re-renders and anything it returned
 * lands nowhere. The confirmation has to survive the thing that caused it, so it
 * travels in the URL.
 *
 * No reason is asked for here, and that asymmetry is deliberate (ADR-071 §4).
 * Agreeing with the scheduler explains itself; disagreeing with it does not, and
 * the rejection route requires a sentence for exactly the reason ADR-059 gives.
 */
import type { NextRequest } from "next/server";

import { callApi } from "@/lib/api";
import { seeOther } from "@/lib/redirect";

export async function POST(request: NextRequest): Promise<Response> {
  const form = await request.formData();
  const ref = String(form.get("ref") ?? "");

  const back = (query: string): Response => seeOther(`/overview?${query}`);

  if (ref === "") {
    return back(`error=${encodeURIComponent("ไม่รู้ว่าจะยืนยันงานไหน")}`);
  }

  const response = await callApi(
    `/dispatch/proposals/${encodeURIComponent(ref)}/confirm`,
    { method: "POST" },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    const detail =
      typeof body.detail === "string" ? body.detail : `ระบบตอบกลับ ${response.status}`;
    return back(`error=${encodeURIComponent(detail)}`);
  }

  return back(`confirmed=${encodeURIComponent(ref)}`);
}

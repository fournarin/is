/**
 * Let one held ticket through, with a reason.
 *
 * A plain HTML form posts here and is redirected back, rather than a server
 * action returning state. That is not a style choice: a successful release
 * takes the ticket out of the held list, so the component that submitted no
 * longer exists when the page re-renders, and anything it returned lands
 * nowhere. The confirmation has to survive the thing that caused it, so it
 * travels in the URL.
 *
 * The reason is required here and at the API (ADR-059). An override with no
 * reason is indistinguishable from a bug when somebody reads it back six weeks
 * later, and reading it back is the entire value of the record.
 */
import type { NextRequest } from "next/server";

import { callApi } from "@/lib/api";
import { seeOther } from "@/lib/redirect";

export async function POST(request: NextRequest): Promise<Response> {
  const form = await request.formData();
  const ref = String(form.get("ref") ?? "");
  const reason = String(form.get("reason") ?? "").trim();

  const back = (query: string): Response =>
    seeOther(`/overview?${query}`);

  if (ref === "") {
    return back(`error=${encodeURIComponent("ไม่รู้ว่าจะปล่อยงานไหน")}`);
  }
  if (reason === "") {
    return back(`error=${encodeURIComponent("เขียนเหตุผลสั้น ๆ ก่อนปล่อยงานนี้")}`);
  }

  const response = await callApi(`/dispatch/held/${encodeURIComponent(ref)}/release`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    const detail =
      typeof body.detail === "string" ? body.detail : `ระบบตอบกลับ ${response.status}`;
    return back(`error=${encodeURIComponent(detail)}`);
  }

  return back(`released=${encodeURIComponent(ref)}`);
}

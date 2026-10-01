/**
 * Not now, and here is why - and the job is set aside for the rest of the shift
 * (ADR-120). The crew is freed at once; the lead can bring it back from the board.
 *
 * The reason is required here and at the API (ADR-059, ADR-071 §4). A rejection
 * with no reason is indistinguishable from a misclick when somebody reads it
 * back six weeks later, and reading it back - proposal by proposal, what the
 * scheduler said and what the shift lead said - is the entire evidence for
 * whether this step can ever be turned off.
 */
import type { NextRequest } from "next/server";

import { callApi } from "@/lib/api";
import { orUnreachable, seeOther } from "@/lib/redirect";

export function POST(request: NextRequest): Promise<Response> {
  return orUnreachable(() => handle(request));
}

async function handle(request: NextRequest): Promise<Response> {
  const form = await request.formData();
  const ref = String(form.get("ref") ?? "");
  const reason = String(form.get("reason") ?? "").trim();

  const back = (query: string): Response => seeOther(`/board?${query}`);

  if (ref === "") {
    return back(`error=${encodeURIComponent("ไม่รู้ว่าจะพักงานไหน")}`);
  }
  if (reason === "") {
    return back(`error=${encodeURIComponent("เขียนเหตุผลสั้น ๆ ก่อนพักงานนี้")}`);
  }

  const response = await callApi(`/dispatch/proposals/${encodeURIComponent(ref)}/reject`, {
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

  return back(`rejected=${encodeURIComponent(ref)}`);
}

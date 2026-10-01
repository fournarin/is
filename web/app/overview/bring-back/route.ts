/**
 * The shift lead takes back their own "not now" (ADR-120). The next round ranks
 * the job again; nothing is sent to anybody from here.
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
  const back = (query: string): Response => seeOther(`/board?${query}`);
  if (ref === "") {
    return back(`error=${encodeURIComponent("ไม่รู้ว่าจะนำงานไหนกลับมา")}`);
  }
  const response = await callApi(`/dispatch/set-aside/${encodeURIComponent(ref)}/bring-back`, {
    method: "POST",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    const detail = typeof body.detail === "string" ? body.detail : `ระบบตอบกลับ ${response.status}`;
    return back(`error=${encodeURIComponent(detail)}`);
  }
  return back(`brought=${encodeURIComponent(ref)}`);
}

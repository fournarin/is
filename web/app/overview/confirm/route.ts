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
 *
 * With an `assignee`, the job goes out now to that person instead of the one the
 * round chose (ADR-132). The API checks they may take it and records it as a
 * disagreement about the person; the banner names who it went to.
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
  const assignee = String(form.get("assignee") ?? "");

  const back = (query: string): Response => seeOther(`/board?${query}`);

  if (ref === "") {
    return back(`error=${encodeURIComponent("ไม่รู้ว่าจะยืนยันงานไหน")}`);
  }

  const response = await callApi(
    `/dispatch/proposals/${encodeURIComponent(ref)}/confirm`,
    assignee === ""
      ? { method: "POST" }
      : {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ assignee }),
        },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    const detail =
      typeof body.detail === "string" ? body.detail : `ระบบตอบกลับ ${response.status}`;
    return back(`error=${encodeURIComponent(detail)}`);
  }

  if (assignee !== "") {
    const answered = (await response.json().catch(() => ({}))) as {
      given_to?: unknown;
    };
    const names = Array.isArray(answered.given_to)
      ? answered.given_to.map(String).join(", ")
      : "";
    if (names !== "") {
      return back(
        `given=${encodeURIComponent(ref)}&to=${encodeURIComponent(names)}`,
      );
    }
  }
  return back(`confirmed=${encodeURIComponent(ref)}`);
}

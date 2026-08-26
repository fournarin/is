/**
 * Ask the authoring worker for a draft of one symptom (ADR-003, ADR-040).
 *
 * The gaps panel has always been able to say that nothing serves a symptom, and
 * never able to do anything about it: `POST /playbooks/drafts` existed, and the
 * only way to reach it was `/docs` or curl. This is the button between them.
 *
 * A route handler with a plain form rather than a server action, like the
 * confirm and release routes beside it, so it works on a phone whose JavaScript
 * never arrived - and because the answer has to survive a re-render of the list
 * it was pressed from.
 *
 * The question is typed by the engineer and not derived from the symptom code.
 * That is ADR-040's finding, held in the shape of the form: `SYM-014` retrieves
 * nothing, and "belt motor running above 85 degrees" retrieves the page.
 */
import type { NextRequest } from "next/server";

import { callApi } from "@/lib/api";
import { seeOther } from "@/lib/redirect";

export async function POST(request: NextRequest): Promise<Response> {
  const form = await request.formData();
  const symptomCode = String(form.get("symptom_code") ?? "");
  const machineModel = String(form.get("machine_model") ?? "");
  const question = String(form.get("question") ?? "").trim();

  const back = (query: string): Response => seeOther(`/overview?${query}`);

  if (symptomCode === "" || machineModel === "") {
    return back(`error=${encodeURIComponent("ไม่รู้ว่าจะร่างของอาการไหน")}`);
  }
  if (question === "") {
    return back(
      `error=${encodeURIComponent(
        "พิมพ์สิ่งที่จะถามคู่มือด้วย — รหัสอาการอย่างเดียวค้นไม่เจอหน้าไหน",
      )}`,
    );
  }

  const response = await callApi("/playbooks/drafts", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      symptom_code: symptomCode,
      machine_model: machineModel,
      question,
    }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    const detail =
      typeof body.detail === "string" ? body.detail : `ระบบตอบกลับ ${response.status}`;
    return back(`error=${encodeURIComponent(detail)}`);
  }

  // 202 either way: asking twice for something already coming is not an error,
  // and the answer says which happened so the screen can too (ADR-040).
  const queued = (await response.json().catch(() => ({}))) as { queued_already?: boolean };
  const already = queued.queued_already === true ? "&already=1" : "";
  return back(`drafting=${encodeURIComponent(symptomCode)}${already}`);
}

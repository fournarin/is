"use server";

import { redirect } from "next/navigation";

import { callApi } from "@/lib/api";

export type DecisionState = { error: string | null; thai?: string[]; thaiTools?: string[] };

/**
 * What the API said, turned into something a reviewer can act on.
 *
 * Every one of these is a refusal the endpoint made on purpose, so none of them
 * is reported as "something went wrong": a 403 means this account may look and
 * not decide (ADR-024), and a 409 means somebody else got there first, which is
 * an ordinary thing to happen to a queue two engineers are working.
 */
async function refusal(response: Response): Promise<string> {
  if (response.status === 403) {
    return "บัญชีนี้ดูคิวได้ แต่ตัดสินไม่ได้ — เฉพาะวิศวกรเท่านั้นที่อนุมัติได้ (ADR-024)";
  }
  if (response.status === 409) {
    return "ใบนี้ถูกตัดสินไปแล้ว ลองโหลดคิวใหม่";
  }
  if (response.status === 422) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof body?.detail === "string" ? body.detail : null;
    return detail ?? "ระบบไม่รับคำสั่งนี้ ตรวจสิ่งที่กรอกอีกครั้ง";
  }
  return `ระบบตอบกลับผิดปกติ (${response.status})`;
}

function proposalId(form: FormData): number {
  return Number(form.get("proposal_id") ?? 0);
}

/**
 * Approve, with or without the reviewer's own wording.
 *
 * One action for both buttons, because they are one decision: "edit and
 * approve" is an approval that carries a diff, and giving it a second endpoint
 * would let the two drift apart until one of them forgot to store the diff
 * (ADR-064).
 *
 * `steps` is sent only when something was actually rewritten. An unchanged
 * draft approved through the edit form would otherwise arrive as an edit of
 * every step to itself, and the edit rate - which is a number in the report -
 * would count it.
 */
export async function approve(
  _previous: DecisionState,
  form: FormData,
): Promise<DecisionState> {
  const id = proposalId(form);
  const original = form.getAll("original").map(String);
  const rewritten = form.getAll("step").map(String);
  const changed = rewritten.length === original.length && rewritten.some(
    (text, index) => text !== original[index],
  );

  const skill = String(form.get("required_skill") ?? "").trim();
  const minutes = String(form.get("estimated_minutes") ?? "").trim();
  const technicians = String(form.get("required_technicians") ?? "").trim();
  const note = String(form.get("note") ?? "").trim();

  const body: Record<string, unknown> = {};
  if (changed) {
    body.steps = rewritten;
  }
  // Position for position, blanks included, so step three's Thai stays step
  // three's (ADR-095). Sent only when somebody wrote any.
  const thai = form.getAll("thai").map((one) => String(one).trim());
  if (thai.some((one) => one !== "")) {
    body.thai_steps = thai;
  }
  const thaiTools = form.getAll("thai_tool").map((one) => String(one).trim());
  if (thaiTools.some((one) => one !== "")) {
    body.thai_tools = thaiTools;
  }
  if (skill !== "") {
    body.required_skill = skill;
  }
  if (minutes !== "") {
    body.estimated_minutes = Number(minutes);
  }
  if (technicians !== "") {
    body.required_technicians = Number(technicians);
  }
  if (note !== "") {
    body.note = note;
  }

  const response = await callApi(`/playbooks/queue/${id}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    // Handed back so a refusal over one figure does not wipe every other
    // rendering the engineer typed (ADR-102).
    return {
      error: await refusal(response),
      thai: form.getAll("thai").map(String),
      thaiTools: form.getAll("thai_tool").map(String),
    };
  }
  redirect("/review?done=approved");
}

/**
 * The draft is wrong: refuse it and ask again, in the reviewer's words.
 *
 * The note is required here as well as at the endpoint, so that a press with an
 * empty box does not become a round trip that was always going to fail. It is
 * also the question the next drafting attempt is given, which is the whole
 * reason the button is not a second dismiss (ADR-064).
 */
export async function sendBack(
  _previous: DecisionState,
  form: FormData,
): Promise<DecisionState> {
  const note = String(form.get("note") ?? "").trim();
  if (note === "") {
    return { error: "เขียนสั้น ๆ ว่าฉบับนี้ผิดตรงไหน ข้อความนี้จะกลายเป็นคำถามของการร่างรอบหน้า" };
  }

  const response = await callApi(`/playbooks/queue/${proposalId(form)}/send-back`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!response.ok) {
    // Handed back so a refusal over one figure does not wipe every other
    // rendering the engineer typed (ADR-102).
    return { error: await refusal(response), thai: form.getAll("thai").map(String) };
  }
  redirect("/review?done=returned");
}

/**
 * Not relevant, on the record.
 *
 * A note is required for the reason ADR-038 section 6 gives: the dismissals are
 * what answer "why does this symptom still have no playbook when three people
 * have looked at it", and a queue of unexplained refusals answers nothing.
 */
export async function dismiss(
  _previous: DecisionState,
  form: FormData,
): Promise<DecisionState> {
  const note = String(form.get("note") ?? "").trim();
  if (note === "") {
    return { error: "เขียนสั้น ๆ ว่าทำไมใบนี้ไม่เกี่ยว" };
  }

  const response = await callApi(`/playbooks/queue/${proposalId(form)}/dismiss`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!response.ok) {
    // Handed back so a refusal over one figure does not wipe every other
    // rendering the engineer typed (ADR-102).
    return { error: await refusal(response), thai: form.getAll("thai").map(String) };
  }
  redirect("/review?done=dismissed");
}

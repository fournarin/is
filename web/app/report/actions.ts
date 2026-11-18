"use server";

import { callApi } from "@/lib/api";
import { openOrdersIn, openReasonsIn, openTitlesIn } from "@/lib/open-orders";
import { revalidatePath } from "next/cache";

export type ReportState = {
  error: string | null;
  /** Tickets already open on that machine. Empty unless the API refused with them. */
  openOrders: string[];
  /** One line per open ticket, aligned with `openOrders`, for the warning. */
  openLines: string[];
  /** The ticket this report became, once it has become one. */
  created: string | null;
  /** What became of the photo, once the report exists: null when none was sent. */
  photo: { kept: boolean; said: string } | null;
  /**
   * What was answered, sent back so a refusal does not empty the form.
   *
   * On the JavaScript path React leaves the inputs alone and this changes
   * nothing. Without it the page is rendered again from scratch, and somebody
   * standing at a machine who is told "that machine already has work open"
   * would have to answer again before they could say it is something else -
   * which is how a refusal becomes an abandoned report. A photo cannot be sent
   * back; it is taken again.
   */
  values: { machineId: string; stopped: string; seen: string[]; typed: string; severity: string };
};

/**
 * The words the report is stored in, from the answers (REQ-P-01, REQ-P-04).
 *
 * Whether the machine is stopped is its own question and goes first, so the
 * technician and the board read it before anything else; the description field
 * is the only place it can live until the API has a field for it (REQ-P-04, B).
 */
function described(stopped: string, seen: string[], typed: string): string {
  const state = stopped === "yes" ? "เครื่องหยุดอยู่" : stopped === "no" ? "เครื่องยังเดินอยู่" : "";
  return [state, ...seen, typed].filter((part) => part !== "").join(" · ");
}

/**
 * Send what somebody saw, then the photo if there is one, and say what came back.
 *
 * Returns state rather than redirecting, which decides the rest of the shape:
 * every field arrives as a named input rather than through `.bind()`, because a
 * bound action that returns state never finishes its response on the
 * no-JavaScript path - and the phone this is built for is exactly the one whose
 * bundle did not arrive (the lesson `app/work/actions.ts` records).
 *
 * The report and its photo are two requests on purpose: a photo the API refuses
 * (too large, not a picture) must not cost the report, which is the part that
 * matters (ADR-142). The refusals are passed through rather than reworded.
 */
export async function reportFault(_previous: ReportState, form: FormData): Promise<ReportState> {
  const machineId = String(form.get("machine_id") ?? "");
  const stopped = String(form.get("stopped") ?? "");
  const seen = form.getAll("seen").map(String).filter((one) => one !== "");
  const typed = String(form.get("typed") ?? "").trim();
  const severity = String(form.get("severity") ?? "") || "medium";
  const distinctFrom = form
    .getAll("distinct_from")
    .map(String)
    .filter((ref) => ref !== "");

  const nothing: ReportState = {
    error: null,
    openOrders: [],
    openLines: [],
    created: null,
    photo: null,
    values: { machineId, stopped, seen, typed, severity },
  };
  if (machineId === "") {
    return { ...nothing, error: "เลือกเครื่องก่อน" };
  }
  if (stopped === "") {
    return { ...nothing, error: "ตอบก่อนว่าเครื่องหยุดอยู่ไหม" };
  }
  if (seen.length === 0 && typed === "") {
    return { ...nothing, error: "เลือกสิ่งที่เห็นอย่างน้อยหนึ่งข้อ หรือพิมพ์สั้น ๆ" };
  }

  const response = await callApi("/work-orders", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      machine_id: machineId,
      severity,
      description: described(stopped, seen, typed),
      distinct_from: distinctFrom,
    }),
  });

  if (response.status === 201) {
    const created = (await response.json()) as { ref: string };
    const photo = await attachPhoto(created.ref, form.get("photo"));
    // The list of the reporter's own reports sits under this form; without this
    // it said "ยังไม่เคยแจ้ง" right under "รับเรื่องแล้ว" until a reload (ADR-126).
    revalidatePath("/report");
    return { ...nothing, created: created.ref, photo };
  }

  const body = await response.json().catch(() => null);
  if (response.status === 409) {
    const open = openOrdersIn(body);
    const titles = openTitlesIn(body);
    const reasons = openReasonsIn(body);
    // The ticket number alone told the operator nothing; what it is about lets
    // them judge "same fault or not" (ADR-126). One line each, by machine and
    // symptom: the reasons run together were unreadable (finding 20).
    const lines = open.map((ref, index) => {
      const about = titles[index] || reasons[index];
      return about ? `${ref} · ${about}` : ref;
    });
    return {
      ...nothing,
      error: "เครื่องนี้มีงานค้างอยู่แล้ว:",
      openOrders: open,
      openLines: lines,
    };
  }
  if (response.status === 422) {
    return { ...nothing, error: detailOf(body, "ข้อมูลไม่ครบ") };
  }
  return { ...nothing, error: `ระบบตอบกลับผิดปกติ (${response.status})` };
}

async function attachPhoto(ref: string, photo: FormDataEntryValue | null): Promise<ReportState["photo"]> {
  if (!(photo instanceof File) || photo.size === 0) {
    return null;
  }
  const body = new FormData();
  body.append("file", photo, photo.name || "photo.jpg");
  const response = await callApi(`/work-orders/${encodeURIComponent(ref)}/photo`, { method: "POST", body });
  if (response.status === 201) {
    return { kept: true, said: "แนบรูปแล้ว" };
  }
  const detail = detailOf(await response.json().catch(() => null), `ระบบไม่รับรูป (${response.status})`);
  return { kept: false, said: `ไม่ได้แนบรูป: ${detail}` };
}

function detailOf(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  // FastAPI answers a schema refusal with a list of problems and our own
  // refusals with one sentence. Both are shown as they are: the sentence is
  // the one ADR-077 wrote to be read at a machine.
  const message = Array.isArray(detail)
    ? String((detail[0] as { msg?: unknown })?.msg ?? fallback)
    : String(detail ?? fallback);
  return message.replace(/^Value error, /, "");
}

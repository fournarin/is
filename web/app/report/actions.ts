"use server";

import { callApi } from "@/lib/api";
import { openOrdersIn } from "@/lib/open-orders";

export type ReportState = {
  error: string | null;
  /** Tickets already open on that machine. Empty unless the API refused with them. */
  openOrders: string[];
  /** The ticket this report became, once it has become one. */
  created: string | null;
};

/**
 * Send what somebody saw, and say what came back.
 *
 * Returns state rather than redirecting, which decides the rest of the shape:
 * every field arrives as a named input rather than through `.bind()`, because a
 * bound action that returns state never finishes its response on the
 * no-JavaScript path - and the phone this is built for is exactly the one whose
 * bundle did not arrive (the lesson `app/work/actions.ts` records).
 *
 * The refusals are passed through rather than reworded. The API's message says
 * which rule refused and what to do instead, and a second phrasing here would be
 * the one that goes stale (ADR-005's argument about the ticket's reason, applied
 * to the screen).
 */
export async function reportFault(_previous: ReportState, form: FormData): Promise<ReportState> {
  const machineId = String(form.get("machine_id") ?? "");
  const severity = String(form.get("severity") ?? "");
  const description = String(form.get("description") ?? "").trim();
  const distinctFrom = form
    .getAll("distinct_from")
    .map(String)
    .filter((ref) => ref !== "");

  const nothing: ReportState = { error: null, openOrders: [], created: null };
  if (machineId === "") {
    return { ...nothing, error: "เลือกเครื่องก่อน" };
  }
  if (description === "") {
    return { ...nothing, error: "เขียนสั้น ๆ ว่าเห็นอะไร" };
  }

  const response = await callApi("/work-orders", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      machine_id: machineId,
      severity,
      description,
      distinct_from: distinctFrom,
    }),
  });

  if (response.status === 201) {
    const created = (await response.json()) as { ref: string };
    return { error: null, openOrders: [], created: created.ref };
  }

  const body = await response.json().catch(() => null);
  if (response.status === 409) {
    const open = openOrdersIn(body);
    return {
      error:
        `เครื่องนี้มีงานค้างอยู่แล้ว: ${open.join(", ")} — ` +
        "ถ้าเป็นเรื่องเดียวกัน ไม่ต้องแจ้งซ้ำ ถ้าคนละเรื่อง กดยืนยันด้านล่าง",
      openOrders: open,
      created: null,
    };
  }
  if (response.status === 422) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    // FastAPI answers a schema refusal with a list of problems and our own
    // refusals with one sentence. Both are shown as they are: the sentence is
    // the one ADR-077 wrote to be read at a machine.
    const message = Array.isArray(detail)
      ? String((detail[0] as { msg?: unknown })?.msg ?? "ข้อมูลไม่ครบ")
      : String(detail ?? "ข้อมูลไม่ครบ");
    return { ...nothing, error: message.replace(/^Value error, /, "") };
  }
  return { ...nothing, error: `ระบบตอบกลับผิดปกติ (${response.status})` };
}

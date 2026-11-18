"use client";

import { ArrowRight, Camera, Check, CircleAlert, CircleCheck, ImageOff, Pencil } from "lucide-react";
import { useActionState, useRef, useState, type ChangeEvent, type FormEvent } from "react";

import { type ReportState, reportFault } from "@/app/report/actions";

// Here rather than in `actions.ts`: a `"use server"` file may only export async
// functions, and a constant beside the action is the mistake that shape invites.
const NOTHING_REPORTED: ReportState = {
  error: null,
  openOrders: [],
  openLines: [],
  created: null,
  photo: null,
  values: { machineId: "", stopped: "", seen: [], typed: "", severity: "medium" },
};

// REQ-P-01: what an operator sees, as taps rather than typing. Words for things
// seen and heard, never a diagnosis (ADR-077 section 4).
const SEEN = ["รั่ว / ซึม", "เสียงผิดปกติ", "ร้อน / มีกลิ่นไหม้", "มีไฟเตือนที่เครื่อง"];

// ADR-077 §2. `critical` is not offered: a stopped line is andon or radio, and
// the note under the form says so.
const LEVELS = [
  { value: "low", label: "ไม่ด่วน" },
  { value: "medium", label: "ควรดู" },
  { value: "high", label: "ด่วน" },
];

// The long side of the photo once shrunk (ADR-142). Enough to read a label or
// see a drip; a phone's own picture is four times this and a few megabytes.
const PHOTO_EDGE = 1600;

/** Shrink a picture on the phone, so a report with a photo is a few hundred kilobytes over Wi-Fi on the floor. */
async function shrunk(file: File): Promise<File> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, PHOTO_EDGE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((done) => canvas.toBlob(done, "image/jpeg", 0.8));
  return blob === null ? file : new File([blob], "photo.jpg", { type: "image/jpeg" });
}

/**
 * The one screen in this system where a person tells it something it did not
 * already know (REQ-P-01).
 *
 * Three questions answered by taps - is it stopped, what did you see, how
 * urgent - and an optional photo. From a machine's QR that is three taps to a
 * report. Without JavaScript every answer is still a plain input and the form
 * still posts; the photo then goes up as taken, and the API refuses it if it is
 * too large without refusing the report.
 */
export function ReportForm({ machineId, machineLabel, already }: { machineId: string; machineLabel: string; already: string | null }) {
  const [state, action, pending] = useActionState(reportFault, NOTHING_REPORTED);
  const [answers, setAnswers] = useState<{ stopped: boolean; seen: boolean } | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const photo = useRef<HTMLInputElement>(null);
  // The shrunk picture, kept here as well as in the input: React resets a form
  // after its action, and a file input has no default to come back to, so an
  // "already open" answer would otherwise drop the photo just taken.
  const kept = useRef<File | null>(null);

  // No `key` on the form: a refusal ("this machine already has work open") must
  // not remount it, or the photo just taken would be dropped with the DOM. The
  // echoed values below are for the no-JavaScript path, whose page comes back
  // as fresh HTML.
  const values = state.values.machineId === machineId ? state.values : NOTHING_REPORTED.values;

  if (state.created !== null) {
    return (
      <div className="rp-sent">
        <div className="callout is-ok" role="status">
          <CircleCheck size={24} aria-hidden />
          <div>
            <b>
              ส่งแล้ว · <span className="code">{state.created}</span>
            </b>
            <p className="muted">หัวหน้ากะยืนยันก่อนส่งถึงช่าง · ติดตามสถานะได้ด้านล่าง</p>
            {state.photo && (
              <p className={state.photo.kept ? "muted" : undefined}>{state.photo.said}</p>
            )}
          </div>
        </div>
        {/* A plain link, so the page is drawn again with an empty form: a
            second fault seen on the same walk is common (finding 19). */}
        <a className="btn" href={`/report?machine=${encodeURIComponent(machineId)}`}>
          แจ้งอีกเรื่องที่เครื่องนี้
        </a>
        <a className="btn" href="/report">
          แจ้งเครื่องอื่น
        </a>
      </div>
    );
  }

  // What is still unanswered, said under the button rather than discovered by
  // pressing it. Before the first change it is read from what was echoed back.
  const now = answers ?? { stopped: values.stopped !== "", seen: values.seen.length > 0 || values.typed !== "" };
  const missing = [!now.stopped && "เครื่องหยุดอยู่ไหม", !now.seen && "เห็นอะไร"].filter(Boolean) as string[];

  function changed(event: FormEvent<HTMLFormElement>) {
    const form = new FormData(event.currentTarget);
    setAnswers({
      stopped: form.get("stopped") !== null,
      seen: form.getAll("seen").length > 0 || String(form.get("typed") ?? "").trim() !== "",
    });
  }

  async function picked(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (preview) URL.revokeObjectURL(preview);
    if (!file) {
      kept.current = null;
      setPreview(null);
      return;
    }
    try {
      const small = await shrunk(file);
      kept.current = small;
      const swap = new DataTransfer();
      swap.items.add(small);
      input.files = swap.files;
      setPreview(URL.createObjectURL(small));
    } catch {
      // A format the browser cannot draw: it goes up as taken, and the API decides.
      kept.current = file;
      setPreview(null);
    }
  }

  function dropPhoto() {
    kept.current = null;
    if (photo.current) photo.current.value = "";
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
  }

  // Put the kept picture back before the form is read. The action stays the
  // server action itself, not a wrapper: a wrapper is a client function, and the
  // page would then be sent without the action id a phone with no script posts.
  function restorePhoto() {
    const input = photo.current;
    if (kept.current === null || input === null || (input.files?.length ?? 0) > 0) return;
    const swap = new DataTransfer();
    swap.items.add(kept.current);
    input.files = swap.files;
  }

  return (
    <form action={action} onSubmitCapture={restorePhoto} onChange={changed} className="rp">
      <input type="hidden" name="machine_id" value={machineId} />
      {already && (
        <p className="rp-open" role="note">
          {already}
        </p>
      )}
      {state.error !== null && (
        <div className="callout is-bad v-note" role="alert">
          <CircleAlert size={20} aria-hidden />
          <div>
            <b>{state.error}</b>
            {state.openLines.length > 0 && (
              <>
                <ul>
                  {state.openLines.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
                <p>ถ้าเป็นเรื่องเดียวกัน ไม่ต้องแจ้งซ้ำ ถ้าคนละเรื่อง กดส่งอีกครั้ง</p>
              </>
            )}
          </div>
        </div>
      )}

      {/* Carried back into the next submission, so "this is something else" is
          an answer about the tickets the person was actually shown. */}
      {state.openOrders.map((ref) => (
        <input key={ref} type="hidden" name="distinct_from" value={ref} />
      ))}

      <fieldset className="q">
        <legend className="qh">
          <span className="n">1</span>เครื่องหยุดอยู่ไหม<span className="tag req">ต้องตอบ</span>
        </legend>
        <div className="g2">
          {[
            ["yes", "หยุดอยู่"],
            ["no", "ยังเดินอยู่"],
          ].map(([value, label]) => (
            <label className="ch" key={value}>
              <input type="radio" name="stopped" value={value} required defaultChecked={values.stopped === value} />
              <span className="mk" aria-hidden />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="q">
        <legend className="qh">
          <span className="n">2</span>เห็นอะไร<span className="tag req">เลือกได้หลายข้อ</span>
        </legend>
        <div className="g2">
          {SEEN.map((one) => (
            <label className="ch box" key={one}>
              <input type="checkbox" name="seen" value={one} defaultChecked={values.seen.includes(one)} />
              <span className="mk" aria-hidden>
                <Check size={16} strokeWidth={3} />
              </span>
              {one}
            </label>
          ))}
        </div>
        <details className="rp-type" open={values.typed !== "" || undefined}>
          <summary className="btn">
            <Pencil size={20} aria-hidden />
            พิมพ์เพิ่ม (ไม่บังคับ)
          </summary>
          <textarea name="typed" rows={3} defaultValue={values.typed} aria-label="พิมพ์สิ่งที่เห็นเพิ่ม" placeholder="เช่น น้ำมันหยดใต้ฐาน ประมาณฝ่ามือ" />
        </details>
      </fieldset>

      <fieldset className="q">
        <legend className="qh">
          <span className="n">3</span>ด่วนแค่ไหน<span className="tag">ไม่บังคับ</span>
        </legend>
        <div className="rp-urg">
          {LEVELS.map((level) => (
            <label className="ch" key={level.value}>
              <input type="radio" name="severity" value={level.value} defaultChecked={values.severity === level.value} />
              {level.label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="q">
        <legend className="qh">
          <span className="n">4</span>รูปถ่าย<span className="tag">ไม่บังคับ · 1 รูป</span>
        </legend>
        {preview ? (
          <div className="rp-photo">
            {/* eslint-disable-next-line @next/next/no-img-element -- a local object URL, nothing for next/image to optimise */}
            <img src={preview} alt="รูปที่จะส่งไปกับเรื่องนี้" />
            <button type="button" className="btn" onClick={dropPhoto}>
              <ImageOff size={20} aria-hidden />
              เอารูปออก
            </button>
          </div>
        ) : null}
        <label className={`btn rp-cam${preview ? " is-hidden" : ""}`}>
          <Camera size={24} aria-hidden />
          ถ่ายรูปจุดที่เห็น
          <input ref={photo} type="file" name="photo" accept="image/*" capture="environment" onChange={picked} />
        </label>
        <p className="where">ถ่ายเฉพาะเครื่อง ไม่ถ่ายหน้าคน</p>
      </fieldset>

      {/* Under the thumb from the first screen (REQ-P-01: the send button is seen without scrolling at 390x844). */}
      <div className="submit sticky">
        <button type="submit" className={`btn pri${missing.length > 0 ? " off" : ""}`} disabled={pending} aria-disabled={missing.length > 0 || undefined}>
          {pending ? "กำลังส่ง..." : state.openOrders.length > 0 ? "ส่ง: นี่คนละเรื่อง" : `ส่งแจ้งซ่อม ${machineLabel}`}
          {!pending && <ArrowRight size={24} aria-hidden />}
        </button>
        {missing.length > 0 && <p className="miss">ยังต้องตอบ: {missing.join(" · ")}</p>}
      </div>
    </form>
  );
}

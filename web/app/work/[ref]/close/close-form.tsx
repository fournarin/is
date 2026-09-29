"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { BLOCKED_REASONS, OUTCOMES, closeFromForm } from "@/lib/close";
import { type PendingClose, enqueue, pending, settle } from "@/lib/pending-closes";

const OUTCOME_LABELS: Record<(typeof OUTCOMES)[number], string> = {
  fixed: "แก้แล้ว",
  temporary_fix: "แก้ชั่วคราว",
  not_fixed: "ยังไม่หาย",
  // Not a fourth option for symmetry. It is the only false-alarm signal this
  // system will ever get, and the loop that tunes rule thresholds does not
  // exist without it (ADR-022).
  no_problem_found: "ไม่พบปัญหา",
};

const BLOCKED_LABELS: Record<(typeof BLOCKED_REASONS)[number], string> = {
  waiting_parts: "รออะไหล่",
  waiting_line_stop: "รอหยุดสาย",
  waiting_help: "รอคนช่วย",
};

type Sending = "idle" | "sending" | "queued" | "refused";

async function post(ref: string, close: unknown): Promise<"sent" | "offline" | string> {
  try {
    const response = await fetch(`/work/${encodeURIComponent(ref)}/close/send`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(close),
    });
    if (response.ok) {
      return "sent";
    }
    const body = (await response.json().catch(() => ({}))) as { error?: string };
    return body.error ?? `ระบบตอบกลับ ${response.status}`;
  } catch {
    // The request never reached anybody. This is the case the queue is for.
    return "offline";
  }
}

export function CloseForm({ workOrder }: { workOrder: string }) {
  const router = useRouter();
  const [state, setState] = useState<Sending>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [waiting, setWaiting] = useState<PendingClose[]>([]);
  const [blocked, setBlocked] = useState(false);

  /** Try everything the device is holding, and report what is left. */
  const drain = useCallback(async (): Promise<PendingClose[]> => {
    let queue = pending(window.localStorage);
    for (const one of queue) {
      if ((await post(one.ref, one)) === "sent") {
        queue = settle(window.localStorage, one.ref);
      }
    }
    return queue;
  }, []);

  // Synchronising with something outside React - the device's queue and the
  // network - which is what an effect is for. The state lands when the retries
  // come back, never during the render that started them.
  useEffect(() => {
    let live = true;
    const retry = () => {
      void drain().then((left) => {
        if (live) {
          setWaiting(left);
        }
      });
    };
    retry();
    window.addEventListener("online", retry);
    return () => {
      live = false;
      window.removeEventListener("online", retry);
    };
  }, [drain]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    // With JavaScript the queue is possible, so take over. Without it the form
    // posts to the same route on its own and this never runs.
    event.preventDefault();
    const close = closeFromForm(new FormData(event.currentTarget));
    if (close === null) {
      setState("refused");
      setMessage("เลือกก่อนว่างานจบอย่างไร");
      return;
    }

    setState("sending");
    const result = await post(workOrder, close);
    if (result === "sent") {
      settle(window.localStorage, workOrder);
      router.push("/work");
      router.refresh();
      return;
    }
    if (result === "offline") {
      setWaiting(
        enqueue(window.localStorage, {
          ref: workOrder,
          ...close,
          queued_at: new Date().toISOString(),
        }),
      );
      setState("queued");
      setMessage(null);
      return;
    }
    setState("refused");
    setMessage(result);
  }

  if (state === "queued" && !waiting.some((one) => one.ref === workOrder)) {
    // The retry above took it. Saying "not sent" after it went is how a
    // technician ends up closing the job again, or thinking it was lost.
    return (
      <section className="card">
        <h2>✓ ส่งการปิดงานแล้ว</h2>
        <p>เครือข่ายกลับมาแล้ว ระบบได้รับการปิดงาน {workOrder} เรียบร้อย</p>
        <Link className="button-link" href="/work">
          กลับไปที่งานของฉัน
        </Link>
      </section>
    );
  }

  if (state === "queued") {
    return (
      <section className="card">
        <h2>ยังส่งไม่ได้ — เก็บไว้ในเครื่องแล้ว</h2>
        <p>
          เครือข่ายไม่ถึงระบบ การปิดงานนี้ถูกเก็บไว้บนเครื่องและจะส่งเองเมื่อกลับมาต่อได้
          ปิดหน้านี้หรือปิดเครื่องได้ ไม่หาย
        </p>
        <p className="muted">รอส่งอยู่ {waiting.length} รายการ</p>
        <button type="button" onClick={() => void drain().then(setWaiting)}>
          ลองส่งเดี๋ยวนี้
        </button>
      </section>
    );
  }

  return (
    <>
      {waiting.length > 0 && (
        <p className="warning">
          มีการปิดงาน {waiting.length} รายการที่ยังส่งไม่สำเร็จ ระบบจะลองส่งให้เองเมื่อเครือข่ายกลับมา
        </p>
      )}

      <form method="post" action={`/work/${encodeURIComponent(workOrder)}/close/send`} onSubmit={submit}>
        {message !== null && (
          <p className="error" role="alert">
            {message}
          </p>
        )}

        <fieldset className="card">
          <legend>งานจบอย่างไร</legend>
          <div className="chips">
            {OUTCOMES.map((outcome) => (
              <label className="chip" key={outcome}>
                <input type="radio" name="outcome" value={outcome} required />
                <span>{OUTCOME_LABELS[outcome]}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="card">
          <legend>ติดอะไรระหว่างทางไหม</legend>
          <div className="chips">
            {BLOCKED_REASONS.map((reason) => (
              <label className="chip" key={reason}>
                <input
                  type="checkbox"
                  name="blocked_reason"
                  value={reason}
                  onChange={(event) => {
                    if (event.currentTarget.checked) {
                      setBlocked(true);
                    }
                  }}
                />
                <span>{BLOCKED_LABELS[reason]}</span>
              </label>
            ))}
          </div>
          {/* Not the job's duration - that is the sum of the segments (ADR-025).
              This is the part of the elapsed time that was not repair, and it is
              subtracted before anything feeds back into an estimate (ADR-006). */}
          <label className="field minutes">
            <span>ประมาณกี่นาทีที่รออยู่เฉย ๆ</span>
            <input
              type="number"
              name="blocked_minutes"
              min={0}
              max={600}
              step={5}
              defaultValue={0}
              inputMode="numeric"
              aria-hidden={!blocked}
            />
          </label>
        </fieldset>

        <label className="field">
          <span>บันทึกเพิ่มเติม (ไม่บังคับ)</span>
          <textarea name="technician_feedback" rows={2} />
        </label>

        <button type="submit" disabled={state === "sending"}>
          {state === "sending" ? "กำลังปิดงาน..." : "ปิดงาน"}
        </button>
      </form>
    </>
  );
}

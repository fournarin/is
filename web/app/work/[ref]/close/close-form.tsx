"use client";

import { ArrowLeft, ArrowRight, Check, CircleCheck, Lock, SquareCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { BLOCKED_REASONS, type ClosePayload, OUTCOMES, closeFromForm, reachedNobody } from "@/lib/close";
import { type PendingClose, drain as drainQueue, enqueue, settle } from "@/lib/pending-closes";

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
    if (reachedNobody(response.status)) {
      // This server answered and the API behind it did not: the same case as
      // the phone's own network dropping, so the close is kept, not lost.
      return "offline";
    }
    const body = (await response.json().catch(() => ({}))) as { error?: string };
    return body.error ?? `ระบบตอบกลับ ${response.status}`;
  } catch {
    // The request never reached anybody. This is the case the queue is for.
    return "offline";
  }
}

/** What the register says about locks on this job, for the lock question (ADR-135, REQ-H-06). */
export type LockContext = {
  // Your locks still on points of this job, as "ก-03 ที่ CP-3 ใส่ 10:31 น.".
  mine: string[];
  // Anybody's lock still on this job.
  onJob: string[];
  // Whether you put a lock on during this job, so "my locks are off" means something.
  hadMine: boolean;
  // The restore step not yet done, as "ขั้น 6 “...”", when your lock is still on.
  restoreLeft: string | null;
};

const LOCK_LABELS = {
  released: "ปลดกุญแจของฉันแล้ว เครื่องคืนสู่การผลิต",
  still_locked: "ยังล็อกอยู่ (ระบุจุดและเหตุ)",
  not_isolated: "งานนี้ไม่ได้ตัดพลังงาน",
} as const;

const WAITS = [0, 15, 30, 60] as const;

export function CloseForm({
  workOrder,
  locks,
  back,
  backLabel,
  stepsLeft,
}: {
  workOrder: string;
  locks: LockContext;
  back: string;
  backLabel: string;
  stepsLeft: string[];
}) {
  const router = useRouter();
  const [state, setState] = useState<Sending>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [waiting, setWaiting] = useState<PendingClose[]>([]);
  const [waited, setWaited] = useState<string>("0");
  const [answers, setAnswers] = useState<{ outcome: boolean; lock: string | null }>({ outcome: false, lock: null });
  const [review, setReview] = useState<ClosePayload | null>(null);

  /** Try everything the device is holding, and report what is left. */
  const drain = useCallback(
    (): Promise<PendingClose[]> => drainQueue(window.localStorage, post),
    [],
  );

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
    if (close.lock_state === undefined) {
      setState("refused");
      setMessage("ตอบสถานะกุญแจก่อนปิดงาน");
      return;
    }
    // The close is the one action that cannot be taken back: say it once more before it goes (REQ-T-02).
    setMessage(null);
    setReview(close);
  }

  async function send(close: ClosePayload) {

    setState("sending");
    const result = await post(workOrder, close);
    if (result === "sent") {
      settle(window.localStorage, workOrder);
      router.push(`/work?done=closed&ref=${encodeURIComponent(workOrder)}`);
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
      <div className="callout is-ok v-note" role="status">
        <CircleCheck size={20} aria-hidden />
        <div>
          <b>ส่งการปิดงานแล้ว</b> · เครือข่ายกลับมาแล้ว ระบบได้รับการปิดงาน {workOrder} เรียบร้อย
          <p style={{ marginTop: 12 }}>
            <Link className="btn pri" href="/work">
              กลับไปที่งานของฉัน
            </Link>
          </p>
        </div>
      </div>
    );
  }

  if (state === "queued") {
    return (
      <div className="callout is-lock v-note" role="status">
        <Lock size={20} aria-hidden />
        <div>
          <b>ยังส่งไม่ได้ เก็บไว้ในเครื่องแล้ว</b>
          <p>เครือข่ายไม่ถึงระบบ การปิดงานนี้ถูกเก็บไว้บนเครื่องและจะส่งเองเมื่อกลับมาต่อได้ ปิดหน้านี้หรือปิดเครื่องได้ ไม่หาย</p>
          <p className="muted">รอส่งอยู่ {waiting.length} รายการ</p>
          <button type="button" className="btn" style={{ marginTop: 12, background: "var(--sunk)" }} onClick={() => void drain().then(setWaiting)}>
            ลองส่งเดี๋ยวนี้
          </button>
        </div>
      </div>
    );
  }

  if (review !== null) {
    return (
      <section className="q" aria-labelledby="sum-h">
        <h2 className="qh" id="sum-h">
          ตรวจก่อนปิดงาน
        </h2>
        {message !== null && (
          <p className="callout is-bad err" role="alert">
            {message}
          </p>
        )}
        <dl className="v-card sumlist" style={{ paddingTop: 0, paddingBottom: 0 }}>
          <div>
            <dt>ผล</dt>
            <dd>
              <b>{OUTCOME_LABELS[review.outcome]}</b>
            </dd>
          </div>
          <div>
            <dt>รอ</dt>
            <dd>
              <b>{review.blocked_minutes} นาที</b>
              {review.blocked_reason.length > 0 && <small>{review.blocked_reason.map((one) => BLOCKED_LABELS[one]).join(" · ")}</small>}
            </dd>
          </div>
          <div>
            <dt>กุญแจ</dt>
            <dd>
              <b>{review.lock_state ? LOCK_LABELS[review.lock_state] : "-"}</b>
              <small>
                {locks.onJob.length > 0 ? `ทะเบียน: ${locks.onJob.join(", ")}` : "ทะเบียน: ไม่มีกุญแจค้างในงานนี้"}
                {review.lock_reason ? ` · เหตุ: ${review.lock_reason}` : ""}
              </small>
            </dd>
          </div>
          <div>
            <dt>โน้ต</dt>
            <dd>
              <b>{review.technician_feedback ?? "ไม่มีโน้ต"}</b>
            </dd>
          </div>
        </dl>
        {stepsLeft.length > 0 && (
          <div className="q">
            <h3 className="qh">{`ยังไม่ได้ทำ ${stepsLeft.length} ขั้น`}</h3>
            <ol className="v-card gapfree" style={{ paddingTop: 0, paddingBottom: 0 }}>
              {stepsLeft.map((one, index) => (
                <li key={one}>
                  <span className="k">{one.match(/\d+/)?.[0] ?? index + 1}</span>
                  <span>{one.replace(/^ขั้น \d+ · /, "")}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
        <div className="submit">
          <button type="button" className="btn pri" disabled={state === "sending"} onClick={() => void send(review)}>
            <SquareCheck size={24} aria-hidden />
            {state === "sending" ? "กำลังปิดงาน..." : "ยืนยันปิดงาน"}
          </button>
        </div>
        <div style={{ marginTop: 8 }}>
          <button type="button" className="btn" onClick={() => setReview(null)}>
            <ArrowLeft size={24} aria-hidden />
            แก้คำตอบ
          </button>
        </div>
      </section>
    );
  }

  const lockOff = {
    released: locks.mine.length > 0 || !locks.hadMine,
    still_locked: locks.onJob.length === 0,
    not_isolated: locks.onJob.length > 0,
  };
  const lockWhy = {
    released:
      locks.mine.length > 0
        ? locks.restoreLeft
          ? `${locks.restoreLeft.split(" “")[0]} คืนพลังงาน ยังไม่ได้ทำ`
          : "กุญแจของคุณยังล็อกอยู่"
        : !locks.hadMine
          ? "ทะเบียนไม่มีกุญแจของคุณในงานนี้"
          : null,
    still_locked: locks.onJob.length === 0 ? "ทะเบียนไม่มีกุญแจที่ยังล็อกอยู่ในงานนี้" : null,
    not_isolated: locks.onJob.length > 0 ? `ทะเบียนมีกุญแจ ${locks.onJob.join(", ")}` : null,
  };
  const missing = [!answers.outcome && "ผลการซ่อม", answers.lock === null && "สถานะกุญแจ"].filter(Boolean);

  return (
    <>
      {waiting.length > 0 && (
        <p className="callout is-lock v-note">
          <Lock size={20} aria-hidden />
          <span>มีการปิดงาน {waiting.length} รายการที่ยังส่งไม่สำเร็จ ระบบจะลองส่งให้เองเมื่อเครือข่ายกลับมา</span>
        </p>
      )}

      <form
        method="post"
        action={`/work/${encodeURIComponent(workOrder)}/close/send`}
        onSubmit={submit}
        onChange={(event) => {
          const form = event.currentTarget;
          setAnswers({
            outcome: form.querySelector("input[name=outcome]:checked") !== null,
            lock: (form.querySelector("input[name=lock_state]:checked") as HTMLInputElement | null)?.value ?? null,
          });
        }}
      >
        {message !== null && (
          <p className="callout is-bad err v-note" role="alert">
            {message}
          </p>
        )}

        <fieldset className="q">
          <legend className="qh">
            <span className="n">1</span>ผลการซ่อม<span className="tag req">ต้องตอบ</span>
          </legend>
          <div className="g2">
            {OUTCOMES.map((outcome) => (
              <label className="ch" key={outcome}>
                <input type="radio" name="outcome" value={outcome} required />
                <span className="mk" aria-hidden />
                {OUTCOME_LABELS[outcome]}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="q">
          <legend className="qh">
            <span className="n">2</span>รอไปกี่นาที<span className="tag">ค่าเริ่มต้น 0</span>
          </legend>
          {/* Not the job's duration - that is the sum of the segments (ADR-025).
              This is the part of the elapsed time that was not repair, and it is
              subtracted before anything feeds back into an estimate (ADR-006). */}
          <div className="waits">
            {WAITS.map((minutes) => (
              <label className="ch" key={minutes}>
                <input
                  type="radio"
                  name="blocked_minutes"
                  value={minutes}
                  defaultChecked={minutes === 0}
                  onChange={() => setWaited(String(minutes))}
                />
                {minutes}
                <small>{minutes === 0 ? "ไม่ได้รอ" : "นาที"}</small>
              </label>
            ))}
          </div>
          <p className="where">{waited === "0" ? "รอเพราะอะไร · เลือกได้เมื่อรอมากกว่า 0 นาที" : "รอเพราะอะไร"}</p>
          <div className="g2" style={{ marginTop: 8 }}>
            {BLOCKED_REASONS.map((reason) => (
              <label className="ch box" key={reason}>
                <input type="checkbox" name="blocked_reason" value={reason} disabled={waited === "0"} />
                <span className="mk" aria-hidden>
                  <Check size={16} strokeWidth={3} />
                </span>
                {BLOCKED_LABELS[reason]}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="q lockq">
          <legend className="qh">
            <span className="n">3</span>สถานะกุญแจ<span className="tag req">ต้องตอบ</span>
          </legend>
          {locks.mine.length > 0 && (
            <p className="callout v-note" style={{ marginTop: 0, marginBottom: 8 }}>
              <Lock size={20} aria-hidden style={{ color: "var(--stop)" }} />
              <span>
                <b>{`กุญแจ ${locks.mine.join(", ")} ของคุณยังล็อกอยู่`}</b>
                {locks.restoreLeft && ` · ${locks.restoreLeft} ยังไม่ได้ทำ จึงเลือก “ปลดกุญแจแล้ว” ไม่ได้`}
              </span>
            </p>
          )}
          <div className="g1">
            {(Object.keys(LOCK_LABELS) as (keyof typeof LOCK_LABELS)[]).map((answer) => (
              <label className="ch" key={answer}>
                <input type="radio" name="lock_state" value={answer} required disabled={lockOff[answer]} />
                <span className="mk" aria-hidden />
                <span>
                  {LOCK_LABELS[answer]}
                  {lockWhy[answer] && <small>{lockWhy[answer]}</small>}
                </span>
              </label>
            ))}
          </div>
          {locks.onJob.length > 0 && (
            <div className="sub-q">
              <p className="where">
                <b>{locks.onJob.join(", ")}</b> (จากทะเบียน) · เหตุที่ยังล็อก
              </p>
              <div className="g2" style={{ marginTop: 8 }}>
                {BLOCKED_REASONS.map((reason) => (
                  <label className="ch" key={reason}>
                    <input type="radio" name="lock_reason" value={BLOCKED_LABELS[reason]} />
                    <span className="mk" aria-hidden />
                    {BLOCKED_LABELS[reason]}
                  </label>
                ))}
              </div>
            </div>
          )}
        </fieldset>

        <label className="q field">
          <span className="qh">
            <span className="n">4</span>โน้ต<span className="tag">ไม่บังคับ</span>
          </span>
          <textarea name="technician_feedback" rows={3} placeholder="สิ่งที่เจอ หรือสิ่งที่คนถัดไปควรรู้" />
        </label>

        <div className="submit">
          <button type="submit" className={`btn ${missing.length === 0 ? "pri" : ""}`} disabled={state === "sending"}>
            ตรวจสรุปก่อนปิดงาน
            <ArrowRight size={24} aria-hidden />
          </button>
          {missing.length > 0 && <p className="miss">{`ยังต้องตอบ: ${missing.join(" · ")}`}</p>}
        </div>
      </form>
      <div className="after">
        <Link className="btn" href={back}>
          <ArrowLeft size={24} aria-hidden />
          {backLabel}
        </Link>
      </div>
    </>
  );
}

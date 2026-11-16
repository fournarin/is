import { Check, CircleAlert, Lock, Timer } from "lucide-react";

import { Th } from "@/app/ui/v2/frame";
import { Sign } from "@/app/ui/v2/signs";
import { confirmPoint } from "@/app/work/actions";
import { plantTime } from "@/lib/display";
import { SAID, restoredBefore, stillNeeded, waitEnds, type Needed, type Who } from "@/lib/energy";
import type { Step, Ticket } from "@/lib/work";

/**
 * The parts of a step an engineer marked as working on the machine's energy
 * (ADR-135): its signs and signal word, its points confirmed one at a time in
 * order, and its wait. Everything here is drawn from `Step.kind` and the marks
 * on it - never from the words of the step (REQ-H-02) - and every confirmation
 * is a form the API checks, so the order holds without JavaScript.
 */

const ENERGY: Record<string, string> = {
  electrical: "พลังงานไฟฟ้า",
  pneumatic: "พลังงานลม",
  hydraulic: "พลังงานไฮดรอลิก",
  mechanical: "พลังงานกล",
  thermal: "ความร้อน",
  gravity: "แรงโน้มถ่วง",
};

// ISO 7010 warnings whose harm is death or serious injury: the DANGER signal word.
const DANGER = new Set(["W012"]);

// The hazard a sign stands for, as the step's title says it.
const HAZARD_TITLE: Record<string, string> = {
  W017: "ขั้นพื้นผิวร้อน",
  W012: "ขั้นอันตรายจากไฟฟ้า",
};

export function KindHeader({ step, revision }: { step: Step; revision: number | null }) {
  const kind = step.kind ?? "normal";
  if (kind === "normal" && (step.hazards ?? []).length === 0) return null;
  const hazards = step.hazards ?? [];
  const signs = [...(kind === "isolation" ? ["M021"] : []), ...hazards];
  const title =
    kind === "isolation"
      ? "ขั้นตัดพลังงาน"
      : kind === "verify"
        ? "ขั้นตรวจพลังงานเป็นศูนย์"
        : kind === "restore"
          ? "ขั้นคืนพลังงาน"
          : `${HAZARD_TITLE[step.hazards?.[0] ?? ""] ?? "ขั้นที่มีอันตราย"}${step.wait_minutes ? " รอให้ครบเวลา" : ""}`;
  // ISO 3864-2: a signal word only beside a sign, graded by the worst hazard on the step (set 2
  // review W1): electricity, stored or live, is DANGER; a hot surface is CAUTION.
  const word = hazards.some((code) => DANGER.has(code))
    ? ["อันตราย", "sig-danger"]
    : hazards.length > 0
      ? ["ข้อควรระวัง", "sig-caution"]
      : null;
  return (
    <div className={`kindh${signs.length === 0 ? " nosign" : ""}`}>
      {signs.length > 0 && (
        <div className="signs">
          {signs.map((code) => (
            <Sign key={code} code={code} />
          ))}
        </div>
      )}
      <p>
        {word && (
          <>
            <span className={`sig ${word[1]}`}>{word[0]}</span>
            <br />
          </>
        )}
        {title}
        <small>{revision !== null ? `วิศวกรกำหนด · ฉบับที่ ${revision}` : "วิศวกรกำหนด"}</small>
      </p>
    </div>
  );
}

/** Who is asking, for rules that are per person (ADR-136). */
export function whoFor(job: Ticket, you: string): Who {
  return {
    user: you,
    locksOn: (job.locks ?? []).filter((one) => one.work_order_ref === job.ref),
    checks: (job.restore_checks ?? []).map((one) => one.key),
  };
}

/** What this step still needs from you, as the API will judge it. */
export function needed(job: Ticket, number: number, now: Date, you: string): Needed[] {
  const who = whoFor(job, you);
  return stillNeeded(job.steps[number - 1]!, number, job.confirmations ?? [], now, who, restoredBefore(job.steps, number));
}

/** "ยังต้องยืนยัน: ใส่กุญแจ · ตรวจพลังงานเป็นศูนย์", one word per kind of thing left. */
export function neededLine(missing: Needed[]): string {
  return `ยังต้องยืนยัน: ${[...new Set(missing.map((one) => SAID[one.item] ?? one.item))].join(" · ")}`;
}

export function Points({ job, number, you, now }: { job: Ticket; number: number; you: string; now: Date }) {
  const step = job.steps[number - 1]!;
  const kind = step.kind ?? "normal";
  const points = step.isolation_points ?? [];
  if (points.length === 0) return null;
  const missing = needed(job, number, now, you);
  const mine = new Set((job.locks ?? []).filter((one) => one.owner === you).map((one) => one.point_id));
  // The next thing you can do: somebody else's lock is theirs to take off.
  const next = missing.find((one) => !(one.item === "released" && !mine.has(one.point_id)));
  // Done means nothing more is asked of you for it - not that somebody once said so.
  const left = new Set(missing.map((one) => `${one.point_id}|${one.item}`));
  const done = new Set(
    points.flatMap((point) => ["off", "locked", "verified", "released"].map((item) => `${point.point_id}|${item}`)).filter((key) => !left.has(key)),
  );
  (job.restore_checks ?? []).forEach((check) => {
    if (!left.has(`${check.key}|checked`)) done.add(`${check.key}|checked`);
  });
  const heading =
    kind === "isolation"
      ? `จุดตัดพลังงาน ${points.length} จุด · ยืนยันตามลำดับ`
      : kind === "verify"
        ? `ตรวจพลังงานเป็นศูนย์ ${points.length} จุด · ก่อนลงมือ`
        : "คืนพลังงานตามลำดับ · OSHA 1910.147(e)";
  let count = 0;

  return (
    <section className="pts" aria-label={heading}>
      <h2 className="ptsh">{heading}</h2>
      {/* W5: a confirmation is never queued with the device's time - offline it is simply not recorded. */}
      <p className="callout is-bad offline-only" role="status">
        <CircleAlert size={20} aria-hidden />
        <span>
          <b>ยังไม่ได้บันทึก</b> · Wi-Fi หลุด ทำตามใบพิมพ์ แล้วแจ้งหัวหน้ากะ
        </span>
      </p>
      {kind === "restore" && <RestoreChecks job={job} number={number} next={next} done={done} />}
      {points.map((point) => {
        const lock = (job.locks ?? []).find((one) => one.point_id === point.point_id);
        const items = kind === "isolation" ? ["off", "locked"] : kind === "verify" ? ["verified"] : ["released"];
        return (
          <div className="v-card pt" key={point.point_id}>
            <h3>
              <Th>{point.label}</Th>
              <small>{`${ENERGY[point.energy] ?? point.energy} · จุด ${point.point_id}`}</small>
            </h3>
            {items.map((item) => {
              count += 1;
              const key = `${point.point_id}|${item}`;
              const isDone = done.has(key);
              const isNext = next !== undefined && next.point_id === point.point_id && next.item === item;
              const label =
                item === "off"
                  ? `ปิด${point.label} แล้ว`
                  : item === "locked"
                    ? isDone && lock
                      ? `ใส่กุญแจ ${lock.lock_no} และป้ายของฉันแล้ว`
                      : "ใส่กุญแจและป้ายของฉันแล้ว"
                    : item === "verified"
                      ? `ตรวจแล้ว ${point.point_id} พลังงานเป็นศูนย์`
                      : lock && lock.owner !== you
                        ? `ปลดกุญแจ ${lock.lock_no} ที่ ${point.point_id}`
                        : `ปลดกุญแจ${lock ? ` ${lock.lock_no}` : ""} ของฉันที่ ${point.point_id}`;
              const blockedFor =
                item === "released" && lock && lock.owner !== you ? `ปลดได้เฉพาะเจ้าของกุญแจ · ${lock.owner_name}` : null;
              return (
                <div className="seqn" key={key}>
                  <span className={`k${isDone ? " ok" : ""}`} aria-hidden>
                    {count}
                  </span>
                  {isDone ? (
                    <div className="ch box is-on" role="status">
                      <span className="mk">
                        <Check size={16} strokeWidth={3} aria-hidden />
                      </span>
                      <span>
                        <Th>{label}</Th>
                      </span>
                    </div>
                  ) : isNext && blockedFor === null && item === "locked" ? (
                    <LockChooser job={job} number={number} point={point.point_id} />
                  ) : isNext && blockedFor === null ? (
                    <form action={confirmPoint.bind(null, job.ref, number, point.point_id, item)}>
                      <button type="submit" className="ch box">
                        <span className="mk" aria-hidden />
                        <span>
                          <Th>{label}</Th>
                        </span>
                      </button>
                    </form>
                  ) : (
                    <div className="ch box off" aria-disabled>
                      <span className="mk" aria-hidden />
                      <span>
                        <Th>{label}</Th>
                        {blockedFor && <small>{blockedFor}</small>}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
    </section>
  );
}

/**
 * The plant's checks before a restore step's locks come off (policy.yaml, R-H5,
 * ADR-136): tools out, guards back, people clear, the operator told. EHS's list,
 * the same on every machine, confirmed by whoever is restoring.
 */
function RestoreChecks({ job, number, next, done }: { job: Ticket; number: number; next: Needed | undefined; done: Set<string> }) {
  const checks = job.restore_checks ?? [];
  if (checks.length === 0) return null;
  return (
    <div className="v-card pt">
      <h3>
        ก่อนจ่ายไฟคืน
        <small>รายการของ จป. ใช้กับทุกเครื่อง</small>
      </h3>
      {checks.map((check, index) => {
        const isDone = done.has(`${check.key}|checked`);
        const isNext = next !== undefined && next.point_id === check.key && next.item === "checked";
        return (
          <div className="seqn" key={check.key}>
            <span className={`k${isDone ? " ok" : ""}`} aria-hidden>
              {index + 1}
            </span>
            {isDone ? (
              <div className="ch box is-on" role="status">
                <span className="mk">
                  <Check size={16} strokeWidth={3} aria-hidden />
                </span>
                <span>{check.label}</span>
              </div>
            ) : isNext ? (
              <form action={confirmPoint.bind(null, job.ref, number, check.key, "checked")}>
                <button type="submit" className="ch box">
                  <span className="mk" aria-hidden />
                  <span>{check.label}</span>
                </button>
              </form>
            ) : (
              <div className="ch box off" aria-disabled>
                <span className="mk" aria-hidden />
                <span>{check.label}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Which personal lock went on: a tap on one used before, or typed once. */
function LockChooser({ job, number, point }: { job: Ticket; number: number; point: string }) {
  const used = (job.your_lock_numbers ?? []).filter((one) => !(job.locks ?? []).some((lock) => lock.lock_no === one));
  return (
    <form className="lockpick" action={confirmPoint.bind(null, job.ref, number, point, "locked")}>
      <p className="lbl">{used.length > 0 ? "กุญแจที่ใส่ · แตะเลือกจากกุญแจของคุณ" : "กุญแจที่ใส่ · พิมพ์เลขกุญแจของคุณ"}</p>
      {used.length > 0 && (
        <div className="g2">
          {used.map((one, index) => (
            <label className="ch" key={one}>
              <input type="radio" name="lock_no" value={one} defaultChecked={index === 0} />
              <span className="mk" aria-hidden />
              {one}
            </label>
          ))}
        </div>
      )}
      <label className="field">
        <span className="lbl">{used.length > 0 ? "หรือพิมพ์เลขอื่น" : "เลขกุญแจ"}</span>
        <input type="text" name="lock_other" autoComplete="off" placeholder="เช่น ก-03" />
      </label>
      <button type="submit" className="ch box">
        <span className="mk" aria-hidden />
        ใส่กุญแจและป้ายของฉันแล้ว
      </button>
    </form>
  );
}

/** A hazard that passes with time: how long is left, from when it started (ADR-135). */
export function WaitBox({ job, number, now, timezone }: { job: Ticket; number: number; now: Date; timezone: string }) {
  const step = job.steps[number - 1]!;
  if (!step.wait_minutes) return null;
  const ends = waitEnds(step, number, job.confirmations ?? []);
  if (ends === null) {
    return (
      <form className="wait" action={confirmPoint.bind(null, job.ref, number, "", "wait_started")}>
        <button type="submit" className="btn">
          <Timer size={24} aria-hidden />
          {`เริ่มนับเวลารอ ${step.wait_minutes} นาที`}
        </button>
      </form>
    );
  }
  const left = Math.max(0, Math.ceil((ends.getTime() - now.getTime()) / 60_000));
  const started = new Date(ends.getTime() - step.wait_minutes * 60_000);
  return (
    <div className="timer" role="timer" aria-live="polite">
      <b>
        {left}
        <small>นาที</small>
      </b>
      <span>
        {left > 0 ? "เหลือ · ระหว่างรอ ห้ามแตะฝาครอบ" : "ครบเวลารอแล้ว · ตรวจก่อนแตะ"}
        <small>
          {"เริ่มรอ "}
          <b>{plantTime(started.toISOString(), timezone)}</b>
          {" · ครบ "}
          <b>{plantTime(ends.toISOString(), timezone)}</b>
        </small>
      </span>
    </div>
  );
}

/** The button that cannot be pressed yet, and why. */
export function NotYet({ missing, label, until }: { missing: Needed[]; label: string; until: string | null }) {
  return (
    <>
      <div className="btn off" aria-disabled>
        <Lock size={24} aria-hidden />
        {until ?? label}
      </div>
      <p className="miss">{neededLine(missing)}</p>
    </>
  );
}

import { Check, Lock } from "lucide-react";

import { releaseMyLock } from "@/app/work/actions";
import { plantTime } from "@/lib/display";
import type { MyLock } from "@/lib/work";

/**
 * Your locks still on, on any job, and the way to record one coming off (ADR-136).
 *
 * After a handover or a "still locked" close the job is no longer yours and its
 * restore step is not yours to confirm, but the lock is still yours - only you
 * take it off. Recording it here, with why and the shift lead who saw it, is how
 * the register ends empty. A job you still hold is restored in its restore step
 * instead, and the API refuses this for it (N1).
 */
export function MyLocks({ locks, timezone }: { locks: MyLock[]; timezone: string }) {
  if (locks.length === 0) return null;
  return (
    <section className="sec" aria-labelledby="locks-h">
      <h2 id="locks-h">{`กุญแจของคุณที่ยังล็อกอยู่ (${locks.length})`}</h2>
      {locks.map((one) => (
        <form className="v-card pt" key={one.lock_id} action={releaseMyLock.bind(null, one.lock_id)}>
          <h3>
            <span className="w">
              <Lock size={20} aria-hidden style={{ display: "inline", verticalAlign: "-3px", marginRight: 8 }} />
              {`${one.lock_no} ที่ ${one.point_id}`}
            </span>
            <small>{`${one.machine_id} · ${one.work_order_ref} · ใส่ ${plantTime(one.applied_at, timezone)} น. ขั้น ${one.step}`}</small>
          </h3>
          {/* C3: the job has closed, so its restore step is gone - the plant's checks are made here. */}
          {!one.job_open && one.checks_needed.length > 0 && (
            <fieldset className="g1" style={{ marginBottom: 8 }}>
              <legend className="lbl">ก่อนจ่ายไฟคืน · ตรวจให้ครบ</legend>
              {one.checks_needed.map((check) => (
                <label className="ch box" key={check.key}>
                  <input type="checkbox" name="checks" value={check.key} required />
                  <span className="mk" aria-hidden>
                    <Check size={16} strokeWidth={3} />
                  </span>
                  {check.label}
                </label>
              ))}
            </fieldset>
          )}
          <label className="field">
            <span className="lbl">เหตุที่ปลด</span>
            <input type="text" name="reason" required placeholder="เช่น คนรับงานใส่กุญแจของตัวเองแล้ว" />
          </label>
          {/* Outside the restore step nothing in the steps vouches for it: the lead who saw it signs (ADR-137). */}
          <div className="g2" style={{ marginTop: 8 }}>
            <label className="field">
              <span className="lbl">หัวหน้ากะที่เห็น</span>
              <input type="text" name="witness" required autoComplete="off" placeholder="ชื่อผู้ใช้" />
            </label>
            <label className="field">
              <span className="lbl">รหัสของหัวหน้ากะ</span>
              {/* C2: never remembered on a shared phone; tries are limited and audited by the API. */}
              <input type="password" name="witness_password" required autoComplete="new-password" data-lpignore="true" data-1p-ignore />
            </label>
          </div>
          <button type="submit" className="btn" style={{ marginTop: 8, background: "var(--sunk)" }}>
            บันทึกว่าปลดกุญแจของฉันแล้ว
          </button>
        </form>
      ))}
    </section>
  );
}

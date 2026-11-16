import { Lock } from "lucide-react";
import type { ReactNode } from "react";

import { plantTime } from "@/lib/display";
import type { LockOn } from "@/lib/work";

/**
 * ISO 7010 safety signs, drawn to ISO 3864 geometry (REQ-H-13). Only the codes
 * an engineer put on a step, and only these three so far: an unknown code is
 * named in text rather than drawn as something it is not. The inventory with
 * codes is this table.
 */
const SIGNS: Record<string, { label: string; svg: ReactNode }> = {
  M021: {
    label: "ISO 7010 M021 ตัดการเชื่อมต่อก่อนซ่อม",
    svg: (
      <svg width="48" height="48" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="48" style={{ fill: "var(--iso-blue)" }} />
        <g fill="#fff">
          <rect x="14" y="40" width="26" height="20" rx="2" />
          <rect x="4" y="44" width="10" height="4" />
          <rect x="4" y="52" width="10" height="4" />
          <rect x="58" y="34" width="26" height="32" rx="2" />
          <rect x="84" y="46" width="8" height="8" />
          <rect x="40" y="47" width="8" height="6" />
        </g>
        <path d="M44 66l12-32" stroke="#fff" strokeWidth="5" />
      </svg>
    ),
  },
  W012: {
    label: "ISO 7010 W012 อันตรายจากไฟฟ้า",
    svg: (
      <svg width="55" height="48" viewBox="0 0 100 88">
        <path d="M50 4L96 84H4z" style={{ fill: "var(--iso-yellow)", stroke: "#000" }} strokeWidth="7" strokeLinejoin="round" />
        <path d="M55 26L36 58h13l-6 20 22-34H52l8-18z" fill="#000" />
      </svg>
    ),
  },
  W017: {
    label: "ISO 7010 W017 พื้นผิวร้อน",
    svg: (
      <svg width="55" height="48" viewBox="0 0 100 88">
        <path d="M50 4L96 84H4z" style={{ fill: "var(--iso-yellow)", stroke: "#000" }} strokeWidth="7" strokeLinejoin="round" />
        <g fill="none" stroke="#000" strokeWidth="4.5" strokeLinecap="round">
          <path d="M38 52c-5-6 5-10 0-17M50 52c-5-6 5-10 0-17M62 52c-5-6 5-10 0-17" />
        </g>
        <rect x="28" y="60" width="44" height="7" fill="#000" />
      </svg>
    ),
  },
};

export function Sign({ code }: { code: string }) {
  const sign = SIGNS[code];
  if (!sign) return <span className="code">{code}</span>;
  return (
    <span role="img" aria-label={sign.label} style={{ display: "block", lineHeight: 0 }}>
      {sign.svg}
    </span>
  );
}

/**
 * Who has a lock on this machine, on which point, since when (REQ-H-07, ADR-135).
 * One line per lock, in the plate's andon voice, on every screen of the job.
 */
export function LockBar({ locks, you, timezone }: { locks: LockOn[]; you: string; timezone: string }) {
  // Whose lock, where, which, since when and from which step - all five (spec; set 2 review S3).
  if (locks.length === 0) return null;
  return (
    <div className="lockbar" role="status">
      <Lock size={20} aria-hidden />
      <span>
        {locks.map((one) => (
          <span key={one.lock_no} style={{ display: "block" }}>
            <b>{`ล็อกอยู่ ${one.point_id}`}</b>
            {" · กุญแจ "}
            <b>{one.lock_no}</b>
            {one.owner === you ? ` ของคุณ (${one.owner_name})` : ` ของ ${one.owner_name}`}
            {` · ใส่ ${plantTime(one.applied_at, timezone)} น. ขั้น ${one.step}`}
          </span>
        ))}
      </span>
    </div>
  );
}

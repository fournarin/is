import Link from "next/link";
import type { ReactNode } from "react";

import { signOut } from "@/app/actions";
import { ROLE_NAMES, type Account } from "@/lib/session";
import { thaiPieces } from "@/lib/thai";

import "./v2.css";

/**
 * Thai that breaks only between words (lib/thai.ts). Each piece is a nowrap span;
 * the spaces between them stay plain text, so the sentence reads, copies and
 * matches exactly as written.
 */
export function Th({ children }: { children: string | null | undefined }) {
  if (!children) return null;
  return (
    <>
      {thaiPieces(children).map((piece, index) =>
        piece.trim() === "" ? (
          piece
        ) : (
          <span className="w" key={index}>
            {piece}
          </span>
        ),
      )}
    </>
  );
}

/**
 * Whether the signals behind these screens are invented (REQ-G-11).
 *
 * Read from the same `SIGNAL_SOURCE` the runtime worker reads: anything but
 * `replay` (a plant's own recorded readings) is synthetic or no signal at all,
 * and either way nothing on the screen came from a real machine.
 */
export function signalsAreSynthetic(): boolean {
  return (process.env.SIGNAL_SOURCE ?? "").trim().toLowerCase() !== "replay";
}

/** The frame of a phone screen: the synthetic banner, a top bar, then the page. */
export function PhoneFrame({ top, children }: { top: ReactNode; children: ReactNode }) {
  return (
    <div className="v2">
      {signalsAreSynthetic() && (
        <div className="synthetic" role="note">
          <span>
            <b>ข้อมูลจำลอง</b> · ไม่ใช่สัญญาณจริง
          </span>
        </div>
      )}
      <header className="top">{top}</header>
      <main className="wrap">{children}</main>
    </div>
  );
}

/** Who is signed in, and the way out. */
export function Who({ account, title }: { account: Account; title: string }) {
  return (
    <>
      <div className="v-who">
        {title}
        <small>
          {account.display_name} · {ROLE_NAMES[account.role]}
        </small>
      </div>
      <form action={signOut} className="out">
        <button type="submit">ออก</button>
      </form>
    </>
  );
}

/** Plant time, from the plant's own zone - never the device's. */
export function Clock({ now, timezone, date = true }: { now: Date; timezone: string; date?: boolean }) {
  const time = new Intl.DateTimeFormat("th-TH", { timeZone: timezone, hour: "2-digit", minute: "2-digit" }).format(now);
  const day = new Intl.DateTimeFormat("th-TH", { timeZone: timezone, day: "numeric", month: "short" }).format(now);
  return (
    <div className="clock" aria-label="เวลาโรงงาน">
      <b>{time}</b>
      {date && <span>วันนี้ {day}</span>}
    </div>
  );
}

/**
 * The sign over the station: its number large, then the machine and the job.
 *
 * `station` is the ticket's own "สถานี 3"; a ticket with none shows the machine
 * alone rather than an invented station.
 */
export function Plate({ station, title, sub }: { station: string | null; title: string; sub: ReactNode }) {
  const number = station?.match(/\d+/)?.[0] ?? null;
  return (
    <div className="aplate">
      <div className="pl">
        {number !== null && (
          <div className="no" aria-label={station ?? undefined}>
            <small>สถานี</small>
            <b>{number}</b>
          </div>
        )}
        <div className="nm">
          <span className="st">
            <Th>{title}</Th>
          </span>
          <span className="mc">{sub}</span>
        </div>
      </div>
    </div>
  );
}

/** One row of a grouped list of other actions: an icon, a label, one quiet line. */
export function Row({ icon, label, sub, href }: { icon: ReactNode; label: string; sub: string; href: string }) {
  return (
    <Link className="rw" href={href}>
      {icon}
      <span className="t">
        <Th>{label}</Th>
        <small>
          <Th>{sub}</Th>
        </small>
      </span>
    </Link>
  );
}

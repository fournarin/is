import Link from "next/link";
import type { ReactNode } from "react";

import { signOut } from "@/app/actions";
import { ROLE_NAMES, type Account } from "@/lib/session";
import { SEVERITY, plantDay, plantTime } from "@/lib/display";
import { thaiPieces } from "@/lib/thai";
import type { Lamp, Ticket } from "@/lib/work";

import { OfflineStrip } from "./offline";
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
      <OfflineStrip />
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

/** The station number from the ticket's own "สถานี 3", or null for a machine the layout does not place. */
export function stationNumber(job: Pick<Ticket, "station">): number | null {
  const found = job.station?.match(/\d+/)?.[0];
  return found === undefined ? null : Number(found);
}

/**
 * The sign over the station: its number large, its name, the machine and the
 * job, and under it the line as lamps with this station lit (ADR-134).
 *
 * A station with no name in `plant.yaml` shows the machine as the title rather
 * than an invented name; lamps that could not be read leave the strip out.
 */
export function Plate({ job, sub, lamps }: { job: Ticket; sub: ReactNode; lamps: Lamp[][] | null }) {
  const number = stationNumber(job);
  const line = number === null ? undefined : lamps?.find((one) => one.some((lamp) => lamp.seq === number));
  return (
    <div className="aplate">
      <div className="pl">
        {number !== null && (
          <div className="no" aria-label={job.station ?? undefined}>
            <small>สถานี</small>
            <b>{number}</b>
          </div>
        )}
        <div className="nm">
          <span className="st">
            <Th>{job.station_name ?? job.machine_id}</Th>
          </span>
          <span className="mc">
            {job.station_name && (
              <>
                <span className="code">{job.machine_id}</span>
                {" · "}
              </>
            )}
            {sub}
          </span>
        </div>
      </div>
      {line && (
        <ol className="pos" aria-label={`ตำแหน่งในสาย: สถานี ${number} จาก ${line.length}`}>
          {line.map((lamp) => (
            <li
              key={lamp.seq}
              className={[lamp.seq === number ? "me" : "", lamp.state === "predicted" ? "fc" : lamp.state === "over_threshold" ? "ov" : ""]
                .join(" ")
                .trim() || undefined}
              title={lamp.name ?? undefined}
            >
              {lamp.seq}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

const DIAMOND =
  "M2.7 10.3a2.41 2.41 0 0 0 0 3.41l7.59 7.59a2.41 2.41 0 0 0 3.41 0l7.59-7.59a2.41 2.41 0 0 0 0-3.41l-7.59-7.59a2.41 2.41 0 0 0-3.41 0Z";

const MARK: Record<Ticket["severity"], ReactNode> = {
  low: <circle cx="12" cy="12" r="10" fill="none" style={{ stroke: "var(--ink)" }} />,
  medium: <path d={DIAMOND} fill="none" style={{ stroke: "var(--ink)" }} />,
  high: <path d={DIAMOND} style={{ fill: "var(--amber)", stroke: "var(--ink)" }} />,
  critical: <rect x="3" y="3" width="18" height="18" rx="2" style={{ fill: "var(--stop)", stroke: "var(--stop)" }} />,
};

/** Priority as shape + word, the same on every screen (design system). */
export function Prio({ severity }: { severity: Ticket["severity"] }) {
  return (
    <span className="prio">
      <svg width="16" height="16" viewBox="0 0 24 24" strokeWidth="2.5" aria-hidden>
        {MARK[severity]}
      </svg>
      <span>{SEVERITY[severity]}</span>
    </span>
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

/** Who approved the steps this order carries, and when (principle 2). */
export function Approved({
  approval,
  timezone,
}: {
  approval: NonNullable<Ticket["approval"]>;
  timezone: string;
}): ReactNode {
  return (
    <p className="prov">
      ขั้นตอน
      {approval.revision !== null && <b>{`ฉบับที่ ${approval.revision}`}</b>}
      {" · อนุมัติโดย "}
      <b>
        <Th>{approval.approved_by}</Th>
      </b>{" "}
      <span className="w">{plantDay(approval.approved_at, timezone)}</span>{" "}
      <span className="w">{`${plantTime(approval.approved_at, timezone)} น.`}</span>
      {approval.manual && (
        <>
          {" · "}
          <span lang="en">{approval.manual}</span>
        </>
      )}
    </p>
  );
}

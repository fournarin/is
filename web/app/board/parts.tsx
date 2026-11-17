import type { ReactNode } from "react";

import { Prio, Th } from "@/app/ui/v2/frame";
import { SheetClose } from "@/app/ui/v2/sheet-close";
import { bandFor, plantTime } from "@/lib/display";
import type { Proposal, Ticket } from "@/lib/work";

/** "สถานี 3 · ติดตั้งหลังคา": the station by its name, never only its number; the machine where the layout has none. */
export function place(job: Ticket): string {
  if (job.station && job.station_name) return `${job.station} · ${job.station_name}`;
  return job.station ?? job.machine_id;
}

/**
 * The job by what is wrong, its machine code left for the drawer (ADR-140 item 3:
 * names first). The backend's title leads with the code; the reason stands in
 * for a ticket written before titles existed.
 */
export function what(job: Ticket): string {
  const title = job.title || job.reason;
  return title.startsWith(`${job.machine_id} `) ? title.slice(job.machine_id.length + 1) : title;
}

/** Cars lost if it waits, as the round counted them (ADR-021, ADR-141); null where the layout cannot say. */
export function cars(one: Proposal): number | null {
  return one.downtime_units === null || one.downtime_units === undefined ? null : Math.round(one.downtime_units);
}

/** The top of every drawer: its name and the way out (the dimmed page closes it too). */
export function Grab({ title }: { title: string }) {
  return (
    <div className="grab">
      <b>{title}</b>
      <SheetClose />
    </div>
  );
}

/**
 * The three answers a lead can give a proposal (ADR-071, ADR-132): yes, yes but to
 * somebody else, and not now - which asks why, because agreeing explains itself
 * and disagreeing does not (ADR-059). Plain forms, posted and redirected.
 */
export function Answers({ one, confirm = true }: { one: Proposal; confirm?: boolean }) {
  const first = one.assignee_names[0];
  return (
    <div className="answers">
      {confirm && (
        <form method="post" action="/overview/confirm">
          <input type="hidden" name="ref" value={one.ref} />
          <button type="submit" className="b pri">
            {first ? `ยืนยันให้ ${first}` : "ยืนยัน"}
          </button>
        </form>
      )}
      {one.others.length > 0 && (
        <section aria-label="ให้คนอื่นทำ">
          <h3>ให้คนอื่นทำ</h3>
          <ul className="give">
            {one.others.map((person) => (
              <li key={person.user}>
                <form method="post" action="/overview/confirm">
                  <input type="hidden" name="ref" value={one.ref} />
                  <input type="hidden" name="assignee" value={person.user} />
                  <button type="submit" className="b">{`ให้ ${person.name}`}</button>
                </form>
              </li>
            ))}
          </ul>
        </section>
      )}
      <form method="post" action="/overview/reject" className="aside">
        <input type="hidden" name="ref" value={one.ref} />
        <label className="field">
          <span className="lh">พักไว้ก่อน · ทำไมยังไม่ควรทำตอนนี้</span>
          <textarea name="reason" rows={2} required placeholder="เช่น รอหยุดสายตอนพักเที่ยง" />
        </label>
        <p className="muted">
          <Th>ระบบจะไม่เสนองานนี้อีกจนจบกะ หรือจนกว่าคุณจะนำกลับมา</Th>
        </p>
        <button type="submit" className="b">
          พักไว้ พร้อมเหตุผลนี้
        </button>
      </form>
    </div>
  );
}

/** One fact in a drawer: a label and what the backend said. */
function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/**
 * Everything about one proposal, behind a tap (ADR-140 item 4): where, why first,
 * what state the machine is in, what waiting costs, whom the system proposes and
 * why them, the ticket - and the answers. Nothing here is composed by the screen;
 * the sentences are the backend's (ADR-005, ADR-063).
 */
export function Drawer({ one, job, timezone }: { one: Proposal; job: Ticket; timezone: string }) {
  const lost = cars(one);
  return (
    <div className="panel" role="dialog" aria-label={`รายละเอียด ${what(job)}`}>
      <Grab title="รายละเอียด" />
      <Prio severity={job.severity} />
      <h2 className="dh">
        <Th>{what(job)}</Th>
      </h2>
      <dl className="bfacts">
        <Fact label="ที่ไหน">
          <Th>{place(job)}</Th> · <span className="code">{job.machine_id}</span>
        </Fact>
        <Fact label="ทำไมก่อน">
          <Th>{one.priority_reason}</Th>
        </Fact>
        <Fact label="สถานะ">
          <Th>{bandFor(job).label}</Th>
          {job.eta_text && (
            <span className="muted sub">
              <Th>{job.eta_text}</Th>
            </span>
          )}
        </Fact>
        {lost !== null && <Fact label="ถ้ารอ">{`สายเสียราว ${lost} คัน`}</Fact>}
        <Fact label="ระบบเสนอ">
          <Th>{[one.assignee_names.join(", "), job.required_skill_name, `ราว ${job.estimated_minutes} นาที`].filter(Boolean).join(" · ")}</Th>
        </Fact>
        {one.assigned_because && (
          <Fact label="ได้งานนี้เพราะ">
            <Th>{one.assigned_because}</Th>
          </Fact>
        )}
        {job.handover_note && (
          <Fact label="ช่างคนก่อนส่งต่อ">
            <Th>{job.handover_note}</Th>
          </Fact>
        )}
        {(job.also_open ?? []).length > 0 && (
          <Fact label="งานอื่นที่เครื่องนี้">
            {(job.also_open ?? []).map((other) => (
              <span className="sub" key={other}>
                <Th>{other}</Th>
              </span>
            ))}
          </Fact>
        )}
        <Fact label="ใบงาน">
          <span className="code">{one.ref}</span>
          {` · เสนอ ${plantTime(one.proposed_at, timezone)} · หมดเวลา ${plantTime(one.expires_at, timezone)}`}
        </Fact>
      </dl>
      <Answers one={one} />
    </div>
  );
}

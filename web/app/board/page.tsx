import { CircleAlert, CircleCheck, Undo2, WifiOff } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { signOut } from "@/app/actions";
import { Answers, Drawer, Grab, cars, place, what } from "@/app/board/parts";
import { KeepFresh } from "@/app/ui/keep-fresh";
import { NotYours, Shell } from "@/app/ui/shell";
import { Prio, Th, signalsAreSynthetic } from "@/app/ui/v2/frame";
import { OfflineWatch } from "@/app/ui/v2/offline";
import { SheetFocus } from "@/app/ui/v2/sheet-focus";
import { bannerFor, type Pressed } from "@/lib/banners";
import { plantTime } from "@/lib/display";
import { tabsFor, homeFor } from "@/lib/screens";
import { ROLE_NAMES, requireAccount } from "@/lib/session";
import {
  activeWork,
  currentRound,
  finishedThisShift,
  lineLamps,
  proposals,
  ticket,
  ticketAt,
  type Lamp,
  type LockOn,
  type Ticket,
} from "@/lib/work";
import "./board.css";

/** The shift as the floor names it; the id where plant.yaml has one this list does not know. */
const SHIFT: Readonly<Record<string, string>> = { morning: "กะเช้า", afternoon: "กะบ่าย", night: "กะดึก" };

const STATUS: Readonly<Record<string, string>> = {
  assigned: "มอบหมายแล้ว",
  in_progress: "กำลังทำ",
  handed_over: "ส่งต่อรอคนรับ",
};

/**
 * The line in one quiet strip: station numbers lit by state - amber solid over the
 * threshold, amber outline forecast, nothing else coloured - and one sentence
 * naming what is lit, so no lamp needs a label of its own (ADR-140 item 2).
 */
function LineStrip({ lines }: { lines: Lamp[][] }) {
  return (
    <>
      {lines.map((lamps, index) => {
        const over = lamps.filter((lamp) => lamp.state === "over_threshold");
        const soon = lamps.filter((lamp) => lamp.state === "predicted");
        return (
          <section className="bline" aria-label="สายการผลิต" key={index}>
            <h2>{lines.length > 1 ? `สายที่ ${index + 1}` : "สายการผลิต"}</h2>
            <ol className="lamps">
              {lamps.map((lamp) => (
                <li
                  key={lamp.seq}
                  className={lamp.state === "over_threshold" ? "over" : lamp.state === "predicted" ? "fc" : undefined}
                  aria-label={`สถานี ${lamp.seq} ${lamp.name ?? ""}`.trim()}
                >
                  <b>{lamp.seq}</b>
                </li>
              ))}
            </ol>
            <p className="say">
              {over.map((lamp, index) => (
                <span key={lamp.seq}>
                  {index > 0 && " · "}
                  <b>
                    <Th>{lamp.name ?? `สถานี ${lamp.seq}`}</Th>
                  </b>{" "}
                  <span className="muted">{`(${lamp.seq})`}</span>
                </span>
              ))}
              {over.length > 0 && <span className="muted"> เกินเกณฑ์</span>}
              {soon.length > 0 && (
                <span>
                  {over.length > 0 && " · "}
                  <span className="muted">คาดว่าจะเกิน</span>{" "}
                  <Th>{soon.map((lamp) => lamp.name ?? `สถานี ${lamp.seq}`).join(", ")}</Th>
                </span>
              )}
              {over.length === 0 && soon.length === 0 && <span className="muted">ทุกสถานีปกติ</span>}
            </p>
          </section>
        );
      })}
    </>
  );
}

/** A tab under the queue: a label and its count on one line, the list in a drawer. */
function Tab({ label, count, children }: { label: string; count: string; children: ReactNode }) {
  return (
    <details className="sheet btab">
      <summary>
        <span>{label}</span> <span className="muted">{count}</span>
      </summary>
      <div className="panel" role="dialog" aria-label={label}>
        <Grab title={label} />
        {children}
      </div>
    </details>
  );
}

type Person = { name: string; jobs: { ref: string; title: string; status: string }[]; proposed: number };

/**
 * The shift lead's board (ADR-093), asking first (ADR-140): the line in one strip,
 * then what is waiting for the lead's answer - the top item as the one focal card,
 * the rest one line each - and everything else behind tabs with a count.
 *
 * Nothing here ranks or phrases anything. The queue is in the order of the score
 * that ranked it, and every sentence was written by the backend (ADR-005, ADR-063).
 * Confirming is one tap; another person or "not now" is a tap away in the drawer,
 * and "not now" asks why (ADR-071, ADR-120, ADR-132).
 */
export default async function BoardPage({
  searchParams,
}: {
  searchParams: Promise<{
    released?: string;
    confirmed?: string;
    rejected?: string;
    brought?: string;
    given?: string;
    to?: string;
    error?: string;
  }>;
}) {
  const account = await requireAccount();
  if (account.role !== "supervisor" && account.role !== "engineer") {
    return (
      <Shell account={account} current="/board">
        <NotYours home={homeFor(account.role)} what="กระดานงานเป็นของหัวหน้ากะ" />
      </Shell>
    );
  }
  const { released, confirmed, rejected, brought, given, to, error } = await searchParams;

  const [round, waiting, active, finished, lamps] = await Promise.all([
    currentRound(),
    proposals(),
    activeWork(),
    finishedThisShift(),
    lineLamps(),
  ]);
  const tz = round.timezone;
  const refs = [
    ...waiting.map((one) => one.ref),
    ...round.held.map((one) => one.ref),
    ...round.set_aside.map((one) => one.ref),
    ...round.unassigned.map((one) => one.ref),
    ...active.map((one) => one.ref),
  ];
  const tickets = new Map<string, Ticket>(
    await Promise.all([...new Set(refs)].map(async (ref) => [ref, await ticket(ref)] as const)),
  );
  const titleOf = (ref: string) => {
    const job = tickets.get(ref);
    return job ? what(job) : ref;
  };

  // What was just pressed, named by machine and symptom (fourth trial, finding 8).
  const pressed = (
    [
      ["confirmed", confirmed],
      ["rejected", rejected],
      ["brought", brought],
      ["released", released],
    ] as const
  ).filter((one): one is readonly [Pressed, string] => one[1] !== undefined);
  const banners = await Promise.all(
    pressed.map(async ([what, ref]) =>
      bannerFor(what, ref, (await ticketAt(ref))?.title, active.find((one) => one.ref === ref)?.assignee_names ?? []),
    ),
  );
  if (given !== undefined) {
    const title = (await ticketAt(given))?.title;
    banners.push(`ส่ง${title ? `งาน ${title}` : ` ${given}`} ให้ ${to ?? "ช่างที่คุณเลือก"} แล้ว`);
  }

  // Most important first, by the score that ranked them (fourth trial).
  const queue = [...waiting].sort((a, b) => b.priority_score - a.priority_score || a.ref.localeCompare(b.ref));
  const [top, ...rest] = queue;
  const soonest = queue.length > 0 ? queue.reduce((a, b) => (a.expires_at < b.expires_at ? a : b)) : null;

  // Who is on the shift, as far as the board can see: people holding work and
  // people the round could give work to. "ว่าง" means nothing in hand yet.
  const people = new Map<string, Person>();
  const person = (user: string, name: string) => {
    if (!people.has(user)) people.set(user, { name, jobs: [], proposed: 0 });
    return people.get(user)!;
  };
  for (const one of active) {
    one.assignees.forEach((user, index) =>
      person(user, one.assignee_names[index] ?? user).jobs.push({ ref: one.ref, title: titleOf(one.ref), status: one.status }),
    );
  }
  for (const one of waiting) {
    one.assignees.forEach((user, index) => person(user, one.assignee_names[index] ?? user).proposed++);
    one.others.forEach((other) => person(other.user, other.name));
  }
  const crew = [...people.values()].sort((a, b) => a.jobs.length - b.jobs.length || a.name.localeCompare(b.name, "th"));
  const free = crew.filter((one) => one.jobs.length === 0).length;

  // Padlocks on now, read from the tickets of the work out on the floor (ADR-136).
  const locks: (LockOn & { title: string })[] = active.flatMap((one) =>
    (tickets.get(one.ref)?.locks ?? []).map((lock) => ({ ...lock, title: titleOf(one.ref) })),
  );

  return (
    <div className="v2 bd">
      <OfflineWatch />
      <SheetFocus />
      <KeepFresh />
      {signalsAreSynthetic() && (
        <div className="synthetic" role="note">
          <span>
            <b>ข้อมูลจำลอง</b> · ไม่ใช่สัญญาณจริง
          </span>
        </div>
      )}
      <div className="app">
        <header className="bhdr">
          <div className="ttl">
            <h1>กระดานงาน</h1>
            <span className="shift">
              {round.shift_id ? (SHIFT[round.shift_id] ?? round.shift_id) : "นอกเวลากะ"}
            </span>
          </div>
          <nav aria-label="หน้าหลัก">
            {tabsFor(account.role).map((tab) => (
              <Link key={tab.href} href={tab.href} aria-current={tab.href === "/board" ? "page" : undefined}>
                {tab.label}
              </Link>
            ))}
          </nav>
          <span className="sp" />
          <div className="clk" aria-label="เวลาโรงงาน">
            <b>{plantTime(round.at, tz)}</b>
          </div>
          <div className="me">
            <span>
              {account.display_name}
              <small>{ROLE_NAMES[account.role]}</small>
            </span>
            <form action={signOut}>
              <button type="submit" className="b">
                ออก
              </button>
            </form>
          </div>
        </header>
        <p className="stale offline-only" role="status">
          <WifiOff size={20} aria-hidden />
          {`ข้อมูลเมื่อ ${plantTime(round.at, tz)} · ระบบไม่ตอบ · ยังยืนยันงานไม่ได้จนกว่าจะเชื่อมต่อได้`}
        </p>

        {lamps && <LineStrip lines={lamps} />}

        {banners.map((said) => (
          <p className="callout is-ok said" role="status" key={said}>
            <CircleCheck size={20} aria-hidden />
            <span>
              <Th>{said}</Th>
            </span>
          </p>
        ))}
        {error !== undefined && (
          <p className="callout is-bad said" role="alert">
            <CircleAlert size={20} aria-hidden />
            <span>
              <Th>{error}</Th>
            </span>
          </p>
        )}

        <section className="dec" aria-labelledby="dh">
          <h2 id="dh">
            {`รอคุณตัดสินใจ ${queue.length} เรื่อง`}
            {soonest && <small>{`เรื่องแรกหมดเวลา ${plantTime(soonest.expires_at, tz)}`}</small>}
          </h2>
          {round.placed.length > 0 && (
            // Queued work the next round will propose (ADR-126).
            <p className="muted bnext">{`รอบถัดไป (ไม่เกิน 5 นาที) ระบบจะเสนออีก ${round.placed.length} งาน`}</p>
          )}

          {top === undefined ? (
            <div className="focal none">
              <p className="what">ไม่มีงานรอยืนยัน</p>
              <p className="muted">
                <Th>{round.summary}</Th>
              </p>
            </div>
          ) : (
            <div className="focal">
              <details className="sheet dw">
                <summary>
                  <Prio severity={tickets.get(top.ref)!.severity} />
                  <span className="what">
                    <Th>{titleOf(top.ref)}</Th>
                  </span>
                  <span className="where">
                    <Th>{place(tickets.get(top.ref)!)}</Th>
                  </span>
                  <span className="cost">
                    {cars(top) !== null && (
                      <span>
                        ถ้ารอ สายเสียราว <b>{cars(top)}</b> คัน
                      </span>
                    )}
                    <span>
                      ระบบเสนอ <b>{top.assignee_names.join(", ")}</b>
                    </span>
                  </span>
                </summary>
                <Drawer one={top} job={tickets.get(top.ref)!} timezone={tz} />
              </details>
              <div className="acts">
                <form method="post" action="/overview/confirm">
                  <input type="hidden" name="ref" value={top.ref} />
                  <button type="submit" className="b pri">
                    {`ยืนยันให้ ${top.assignee_names[0] ?? ""}`.trim()}
                  </button>
                </form>
                <details className="sheet menu">
                  <summary className="b">ให้คนอื่น · พักไว้</summary>
                  <div className="panel" role="dialog" aria-label="ให้คนอื่น หรือพักไว้">
                    <Grab title={titleOf(top.ref)} />
                    <Answers one={top} confirm={false} />
                  </div>
                </details>
              </div>
            </div>
          )}

          {(rest.length > 0 || round.unassigned.length > 0) && (
            <div className="brows">
              {rest.map((one) => {
                const job = tickets.get(one.ref)!;
                const lost = cars(one);
                return (
                  <div className="brow" key={one.ref}>
                    <details className="sheet dw">
                      <summary>
                        <span className="t">
                          <Prio severity={job.severity} />
                          <b>
                            <Th>{titleOf(one.ref)}</Th>
                          </b>
                          <span className="muted">
                            <Th>{place(job)}</Th>
                          </span>
                        </span>
                      </summary>
                      <Drawer one={one} job={job} timezone={tz} />
                    </details>
                    <div className="r">
                      <span className="n">
                        {one.assignee_names.join(", ")}
                        {lost !== null && (
                          <>
                            {" · "}
                            <b>{lost}</b> คัน
                          </>
                        )}
                      </span>
                      <form method="post" action="/overview/confirm">
                        <input type="hidden" name="ref" value={one.ref} />
                        <button type="submit" className="b">
                          ยืนยัน
                        </button>
                      </form>
                    </div>
                  </div>
                );
              })}
              {round.unassigned.map((one) => (
                // Admitted by the gate with nobody free to take it (ADR-102): it must show.
                <div className="brow" key={`free-${one.ref}`}>
                  <details className="sheet dw">
                    <summary>
                      <span className="t">
                        {tickets.get(one.ref) && <Prio severity={tickets.get(one.ref)!.severity} />}
                        <b>
                          <Th>{titleOf(one.ref)}</Th>
                        </b>
                        <span className="muted">รอช่างว่าง</span>
                      </span>
                    </summary>
                    <div className="panel" role="dialog" aria-label="รอช่างว่าง">
                      <Grab title="รอช่างว่าง" />
                      <h2 className="dh">
                        <Th>{titleOf(one.ref)}</Th>
                      </h2>
                      <p className="sub">
                        <Th>{one.why}</Th>
                      </p>
                    </div>
                  </details>
                </div>
              ))}
            </div>
          )}
        </section>

        <nav className="btabs" aria-label="อื่น ๆ ในกะนี้">
          <Tab label="ช่างในกะ" count={`ว่าง ${free} จาก ${crew.length} คน`}>
            <ul className="list">
              {crew.map((one) => (
                <li key={one.name}>
                  <b>{one.name}</b>
                  <span className="muted">
                    {one.jobs.length === 0 ? "ว่าง ยังไม่มีงานในมือ" : `${one.jobs.length} งานในมือ`}
                    {one.proposed > 0 && ` · ระบบเสนอให้อีก ${one.proposed} งาน`}
                  </span>
                  {one.jobs.map((job) => (
                    <span className="sub" key={job.ref}>
                      <Th>{`${STATUS[job.status] ?? job.status} · ${job.title}`}</Th>
                    </span>
                  ))}
                </li>
              ))}
            </ul>
            <p className="muted foot">{`ภาระของกะ: ${round.summary}`}</p>
          </Tab>
          <Tab label="ระบบกันไว้ก่อน" count={`${round.held.length}`}>
            {round.held.length === 0 && <p className="muted">ไม่มีงานถูกกันไว้</p>}
            <ul className="list">
              {round.held.map((one) => (
                <li key={one.ref}>
                  <b>
                    <Th>{titleOf(one.ref)}</Th>
                  </b>
                  <span className="muted">
                    <Th>{one.why}</Th>
                  </span>
                  {/* A plain form, posted and redirected (app/overview/release/route.ts). */}
                  <form method="post" action="/overview/release" className="aside">
                    <input type="hidden" name="ref" value={one.ref} />
                    <label className="field">
                      <span className="lh">ปล่อยงานนี้เลย · ทำไมต้องปล่อยตอนนี้</span>
                      <textarea name="reason" rows={2} required placeholder="เช่น สาย A หยุดรอชิ้นนี้อยู่" />
                    </label>
                    <button type="submit" className="b">
                      ปล่อยงาน พร้อมเหตุผลนี้
                    </button>
                  </form>
                </li>
              ))}
            </ul>
          </Tab>
          <Tab label="คุณพักไว้" count={`${round.set_aside.length}`}>
            {round.set_aside.length === 0 && <p className="muted">ไม่มีงานที่พักไว้</p>}
            <ul className="list">
              {round.set_aside.map((one) => (
                <li key={one.ref} className="split">
                  <span>
                    <b>
                      <Th>{titleOf(one.ref)}</Th>
                    </b>
                    <span className="muted">
                      <Th>{`เหตุผลที่พัก: ${one.why}`}</Th>
                    </span>
                  </span>
                  <form method="post" action="/overview/bring-back">
                    <input type="hidden" name="ref" value={one.ref} />
                    <button type="submit" className="b">
                      <Undo2 size={20} aria-hidden />
                      นำกลับมา
                    </button>
                  </form>
                </li>
              ))}
            </ul>
          </Tab>
          <Tab label="เสร็จแล้ว" count={`${finished.length}`}>
            {finished.length === 0 && <p className="muted">ยังไม่มีงานที่ปิดในกะนี้</p>}
            <ul className="list">
              {finished.map((one) => (
                <li key={one.ref}>
                  <b>
                    <Th>{one.reason}</Th>
                  </b>
                  <span className="muted">
                    <Th>{`${one.outcome} · ${one.by_names.join(", ")} · ปิดเมื่อ ${one.closed_when}`}</Th>
                  </span>
                  {one.note && (
                    <span className="sub">
                      <Th>{`บันทึก: ${one.note}`}</Th>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </Tab>
          <Tab label="ล็อกอยู่" count={`${locks.length}`}>
            {locks.length === 0 && <p className="muted">ไม่มีเครื่องที่ล็อกอยู่ตอนนี้</p>}
            <ul className="list">
              {locks.map((lock) => (
                <li key={`${lock.work_order_ref}-${lock.point_id}-${lock.lock_no}`}>
                  <b>
                    <span className="code">{lock.lock_no}</span> · <span className="code">{lock.point_id}</span> ·{" "}
                    {lock.owner_name}
                  </b>
                  <span className="muted">
                    <Th>{`${lock.title} · ตั้งแต่ ${plantTime(lock.applied_at, tz)} น.`}</Th>
                  </span>
                </li>
              ))}
            </ul>
          </Tab>
        </nav>
      </div>
    </div>
  );
}

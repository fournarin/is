import { ArrowLeft, Camera, ChevronRight } from "lucide-react";
import Link from "next/link";

import { ReportForm } from "@/app/report/report-form";
import { KeepFresh } from "@/app/ui/keep-fresh";
import { Clock, PhoneFrame, Th, Who } from "@/app/ui/v2/frame";
import { homeFor } from "@/lib/screens";
import { type Machine, type Reported, machines, myReports } from "@/lib/report";
import { requireAccount } from "@/lib/session";
import { currentRound } from "@/lib/work";

type Station = { id: string; seq: number; name: string | null; machines: Machine[] };

function stationsOf(floor: Machine[]): Station[] {
  const found = new Map<string, Station>();
  for (const machine of floor) {
    const one = found.get(machine.station_id) ?? { id: machine.station_id, seq: machine.seq, name: machine.station_name ?? null, machines: [] };
    one.machines.push(machine);
    found.set(machine.station_id, one);
  }
  return [...found.values()].sort((a, b) => a.seq - b.seq);
}

/** Where a station's own page is: straight to the form when it has one machine. */
function hrefFor(station: Station): string {
  return station.machines.length === 1
    ? `/report?machine=${encodeURIComponent(station.machines[0]!.machine_id)}`
    : `/report?station=${encodeURIComponent(station.id)}`;
}

/**
 * Reporting a fault, for whoever is standing there (ADR-077 §1, REQ-P-01).
 *
 * Three ways in, all plain links so a phone without its script still gets
 * there: `?machine=` from the QR on the machine (three taps to a report), a
 * station then its machine from a shared screen (five), and the list of
 * stations in line order. No role check on this page, deliberately: the API
 * refuses an anonymous report and records every one that is made (invariant 6).
 *
 * The reporter's own reports show four stages and never a technician's name
 * (REQ-P-05, REQ-P-06).
 */
export default async function ReportPage({ searchParams }: { searchParams: Promise<{ machine?: string; station?: string }> }) {
  const account = await requireAccount();
  const { machine: machineId, station: stationId } = await searchParams;
  const [floor, mine, timezone] = await Promise.all([
    machines(),
    myReports(),
    currentRound().then(
      (round) => round.timezone,
      () => "Asia/Bangkok",
    ),
  ]);
  const stations = stationsOf(floor);
  const machine = floor.find((one) => one.machine_id === machineId) ?? null;
  const station = machine ? stations.find((one) => one.id === machine.station_id)! : (stations.find((one) => one.id === stationId) ?? null);

  const back = machine ? (station && station.machines.length > 1 ? hrefFor(station) : "/report") : station ? "/report" : account.role === "operator" ? null : homeFor(account.role);
  const top = (
    <>
      {back !== null && (
        <Link className="back" href={back}>
          <ArrowLeft size={24} aria-hidden />
          {machine || station ? "สถานี" : "กลับ"}
        </Link>
      )}
      {back === null ? <Who account={account} title="แจ้งซ่อม" /> : <span className="anc">แจ้งซ่อม</span>}
      <Clock now={new Date()} timezone={timezone} />
    </>
  );

  const open = machine ? mine.find((one) => one.machine_id === machine.machine_id && !one.finished) : undefined;
  const already = open
    ? `แจ้งไว้แล้ว ${open.reported_when}: ${open.what || open.reason} · ${open.stages?.[(open.stage ?? 1) - 1] ?? ""} · อาการใหม่ส่งเพิ่มได้`
    : null;

  return (
    <PhoneFrame top={top}>
      {station && (
        <div className="aplate">
          <div className="pl">
            <div className="no" role="img" aria-label={`สถานี ${station.seq}`}>
              <small>สถานี</small>
              <b>{station.seq}</b>
            </div>
            <div className="nm">
              <span className="st">
                <Th>{station.name ?? station.id}</Th>
              </span>
              <span className="mc">{machine ? <span className="code">{machine.machine_id}</span> : `${station.machines.length} เครื่อง · เลือกเครื่องที่เห็นปัญหา`}</span>
            </div>
          </div>
        </div>
      )}

      {machine ? (
        <ReportForm machineId={machine.machine_id} machineLabel={machine.machine_id} already={already} key={machine.machine_id} />
      ) : station ? (
        <section className="q" aria-labelledby="m-h">
          <h2 className="qh" id="m-h">
            เครื่องไหน
          </h2>
          <div className="g1">
            {station.machines.map((one) => (
              <Link className="ch rp-go" key={one.machine_id} href={`/report?machine=${encodeURIComponent(one.machine_id)}`}>
                <span className="t">
                  <span className="code">{one.machine_id}</span>
                  <small>{one.model}</small>
                </span>
                <ChevronRight size={24} aria-hidden />
              </Link>
            ))}
          </div>
        </section>
      ) : (
        <section className="q" aria-labelledby="s-h">
          <h2 className="qh" id="s-h">
            สถานีไหน<span className="tag">หรือสแกน QR ที่เครื่อง</span>
          </h2>
          <div className="rp-stns">
            {stations.map((one) => (
              <Link className="ch rp-go" key={one.id} href={hrefFor(one)}>
                <b className="rp-no">{one.seq}</b>
                <span className="t">
                  <Th>{one.name ?? one.id}</Th>
                  <small>{one.machines.map((m) => m.machine_id).join(" · ")}</small>
                </span>
                <ChevronRight size={24} aria-hidden />
              </Link>
            ))}
          </div>
        </section>
      )}

      <p className="rp-note">
        <b>ระบบนี้เป็นคิวงาน ไม่ใช่ช่องทางฉุกเฉิน</b> · ถ้าสายหยุดหรือมีคนเจ็บ ใช้ andon หรือวิทยุ
      </p>

      {/* What happened to each report, so it can be found again after it was
          sent (ADR-122). In the owner's second trial it could not. */}
      <KeepFresh />
      <section className="sec" aria-labelledby="mine-h">
        <h2 id="mine-h">เรื่องที่คุณแจ้งไว้</h2>
        {mine.length === 0 ? <p className="muted">ยังไม่เคยแจ้ง</p> : <div className="g1">{mine.map((one) => <Report key={one.ref} one={one} />)}</div>}
      </section>
    </PhoneFrame>
  );
}

/** One report and its four stages, read without reading a sentence (REQ-P-05). */
function Report({ one }: { one: Reported }) {
  const stages = one.stages ?? [];
  const at = one.stage ?? 1;
  return (
    <article className="v-card rp-rep">
      {/* What they wrote: two reports on one machine looked identical without it (fourth trial, finding 19). */}
      <p className="rp-what">
        <Th>{one.what || one.reason}</Th>
      </p>
      <p className="muted">
        <span className="code">{one.machine_id}</span> · <span className="code">{one.ref}</span> · แจ้ง {one.reported_when}
        {one.photo && (
          <>
            {" · "}
            <a className="rp-ph" href={`/work/${encodeURIComponent(one.ref)}/photo`}>
              <Camera size={18} aria-hidden />
              รูป
            </a>
          </>
        )}
      </p>
      {stages.length > 0 && (
        <ol className="rp-track" aria-label={`สถานะ: ${stages[at - 1]}`}>
          {stages.map((stage, index) => (
            <li key={stage} className={index + 1 < at ? "is-done" : index + 1 === at ? "cur" : undefined} aria-current={index + 1 === at ? "step" : undefined}>
              <i aria-hidden />
              <Th>{stage}</Th>
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}

import { Fragment } from "react";

import { plantTime } from "@/lib/display";
import { edgeFractions } from "@/lib/line-scale";
import type { Line, Station } from "@/lib/overview";

const MARKERS: Record<Station["state"], string> = {
  normal: "○",
  predicted: "△",
  over_threshold: "●",
};

function spell(minutes: number): string {
  return minutes >= 90 ? `${Math.round(minutes / 60)} ชั่วโมง` : `${Math.round(minutes)} นาที`;
}

/**
 * The line, with the gaps drawn to the buffers rather than to fixed widths.
 *
 * ADR-021 prices downtime per station because a station with twenty units in
 * front of it is not a station at a bottleneck. Drawn as equal boxes a reader
 * cannot see why the ranking is what it is; drawn to scale, a red station with
 * nothing before it explains itself (ADR-063 section 4).
 */
export function LineDiagram({ line }: { line: Line }) {
  const fractions = edgeFractions(line.stations);

  return (
    <>
      <div className="line-scroll">
        <div className="line">
          {line.stations.map((station, index) => (
            <Fragment key={station.station_id}>
              <div className={`station ${station.state}`}>
                <span className="marker" aria-hidden="true">
                  {MARKERS[station.state]}
                </span>
                <span className="station-id">{station.station_id}</span>
                {station.bottleneck && <span className="bottleneck">คอขวด</span>}
              </div>
              {index < line.stations.length - 1 && (
                <div
                  className="gap"
                  style={{ flexGrow: fractions[index] }}
                  title={`บัฟเฟอร์ ${station.buffer_units} ชิ้น`}
                >
                  <span className="gap-units">{station.buffer_units}</span>
                </div>
              )}
            </Fragment>
          ))}
        </div>
      </div>
      <p className="muted legend">
        ● เกินเกณฑ์แล้ว · △ คาดว่าจะถึงเกณฑ์ · ○ ปกติ · ความยาวเส้นคือบัฟเฟอร์ระหว่างสถานีเป็นจำนวนชิ้น
      </p>
    </>
  );
}

/**
 * What is wrong, in words, under the diagram.
 *
 * A marker says *that* something is wrong; a shift lead deciding what to do
 * needs to know which machine and how long. Only the stations that are not
 * normal appear - a list of everything that is fine is a list nobody reads.
 */
export function LineFaults({ line, timezone }: { line: Line; timezone: string }) {
  const faults = line.stations.filter((station) => station.state !== "normal");
  if (faults.length === 0) {
    return <p className="card">ทุกสถานีบนสายนี้ปกติ</p>;
  }

  return (
    <ul className="faults">
      {faults.map((station) => (
        <li key={station.station_id} className={station.state}>
          <strong>
            {station.station_id} · {station.machine_id}
          </strong>
          {station.state === "over_threshold" ? (
            <p>เกินเกณฑ์มาแล้ว {spell(station.over_threshold_minutes ?? 0)}</p>
          ) : (
            // ADR-020: never the ETA without its interval. The response cannot
            // be built without both, and neither can this line.
            <p>
              คาดว่าจะถึงเกณฑ์ราว {plantTime(station.eta ?? "", timezone)} บวกลบ{" "}
              {spell(station.eta_confidence_minutes ?? 0)}
            </p>
          )}
          <p className="muted">
            {station.symptom_code} · {station.component}
            {station.live_findings > 1 && ` · อีก ${station.live_findings - 1} อาการที่สถานีนี้`}
            {station.bottleneck && " · คอขวด"}
            {station.buffer_units === 0 && " · ไม่มีบัฟเฟอร์"}
          </p>
        </li>
      ))}
    </ul>
  );
}

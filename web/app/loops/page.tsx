import Link from "next/link";

import { estimateProposals, thresholdProposals } from "@/lib/loops";
import type { ThresholdLine } from "@/lib/loops";
import { ROLE_NAMES, requireAccount } from "@/lib/session";

/**
 * What the finished jobs and the false alarms say, and no button that acts on it.
 *
 * ADR-022 is one sentence - every improvement loop proposes rather than changes -
 * and this screen is where somebody finally reads a proposal. Two things about
 * the layout follow from it:
 *
 * The refusals are shown beside the proposals rather than filtered out. "This
 * threshold is not firing on nothing" and "there is no evidence yet" are
 * different answers, and a screen that rendered both as an empty list would hide
 * the difference (ADR-073 §5, principle 5). The safety-linked rule is the
 * clearest case: its refusal is permanent and is the invariant made visible.
 *
 * Applying either is a person's own act, in the place that records who did it -
 * the playbook's approval for a duration, the rules file for a threshold. So
 * each proposal ends with the edit to make rather than a button, and the exact
 * line is printed for the threshold because a number retyped from memory is the
 * defect the whole screen exists to catch (ADR-087 §3).
 */
export default async function LoopsPage() {
  const account = await requireAccount();
  if (account.role !== "engineer" && account.role !== "supervisor") {
    return (
      <>
        <h1>ข้อเสนอจากงานที่ปิดแล้ว</h1>
        <p className="card">
          หน้านี้เป็นของวิศวกรและหัวหน้ากะ บัญชีนี้เป็น{ROLE_NAMES[account.role]}
        </p>
        <p>
          <Link href="/">กลับหน้าแรก</Link>
        </p>
      </>
    );
  }

  const [estimates, thresholds] = await Promise.all([
    estimateProposals(),
    thresholdProposals(),
  ]);
  const priced = estimates.filter((line) => line.proposal !== null);
  const quiet = estimates.filter((line) => line.proposal === null);
  const proposed = thresholds.filter((line) => line.proposal !== null);
  const refused = thresholds.filter((line) => line.proposal === null);

  return (
    <>
      <div className="who">
        <span>
          ข้อเสนอจากงานที่ปิดแล้ว
          <span className="muted"> · {ROLE_NAMES[account.role]}</span>
        </span>
        <Link href="/">หน้าแรก</Link>
      </div>

      <p className="muted">
        ระบบคำนวณให้ตอนที่เปิดหน้านี้ ไม่ได้เก็บไว้และไม่ได้ตั้งเวลารัน
        ตัวเลขทุกตัวที่นี่เป็นข้อเสนอเท่านั้น — ไม่มีปุ่มไหนแก้ค่าจริงให้
        คนเป็นผู้แก้เอง ในที่ที่บันทึกว่าใครแก้ (ADR-022, ADR-087)
      </p>

      <h1>1 · เวลามาตรฐานของ playbook</h1>
      {priced.length === 0 ? (
        <p className="card">
          ยังไม่มีข้อเสนอ — งานที่ปิดแล้วยังน้อยกว่าเกณฑ์ หรือค่ากลางตรงกับค่าที่ตั้งไว้อยู่แล้ว
        </p>
      ) : (
        priced.map((line) => {
          const one = line.proposal!;
          return (
            <article className="card" key={`${line.symptom_code}/${line.machine_model}`}>
              <div className="screen-head">
                <h2>
                  {line.symptom_code} · {line.machine_model}
                </h2>
                <span className="muted">
                  {one.current_minutes} → {one.proposed_minutes} นาที
                </span>
              </div>
              <p className="reason">{one.reason}</p>
              <p className="muted">
                จาก {one.observations} ใบ · สั้นสุด {one.shortest_minutes} นาที · ยาวสุด{" "}
                {one.longest_minutes} นาที · ค่ากลาง {one.median_minutes} นาที
                {one.no_problem_found > 0 && ` · ไม่พบปัญหา ${one.no_problem_found} ใบ`}
                {one.without_repair_time > 0 &&
                  ` · ไม่มีเวลาทำงานบันทึกไว้ ${one.without_repair_time} ใบ`}
              </p>
              {one.capped && (
                <p className="warning">
                  หลักฐานบอก {one.median_minutes} นาที แต่หนึ่งรอบขยับได้ไม่เกิน 20%
                  แปลว่าค่าที่ตั้งไว้ห่างจากความจริงมากกว่าที่รอบเดียวจะแก้ได้ (ADR-022)
                </p>
              )}
              {line.playbook_status === "needs_review" && (
                <p className="warning">
                  playbook ใบนี้รอรีวิวอยู่ เพราะคู่มือที่อ้างถึงถูกเปลี่ยน
                  แต่ยังถูกส่งให้ช่างและยังใช้คิดโหลดกะอยู่ (ADR-018)
                </p>
              )}
              <p className="muted">
                จะใช้ค่านี้: วิศวกรกรอก {one.proposed_minutes} ตอนอนุมัติ playbook ของคู่นี้ใน{" "}
                <Link href="/review">คิวรีวิว</Link> — การอนุมัติคือที่ที่บันทึกว่าใครเปลี่ยนและเมื่อไร
                (ADR-024)
              </p>
            </article>
          );
        })
      )}
      {quiet.length > 0 && (
        <details className="card">
          <summary>
            อีก {quiet.length} playbook ที่ยังไม่มีข้อเสนอ
          </summary>
          <ul>
            {quiet.map((line) => (
              <li key={`${line.symptom_code}/${line.machine_model}`}>
                {line.symptom_code} · {line.machine_model} — ตั้งไว้ {line.current_minutes} นาที ·
                ปิดแล้ว {line.closed_orders} ใบ
              </li>
            ))}
          </ul>
          <p className="muted">
            &quot;ไม่มีข้อเสนอ&quot; รวมสามกรณีไว้ด้วยกัน: ใบที่ใช้ได้ยังไม่ถึงเกณฑ์ ยังไม่มีเลย
            หรือค่ากลางตรงกับค่าที่ตั้งไว้ หน้านี้ไม่แยกให้
            เพราะการแยกต้องคัดลอกเงื่อนไขว่าใบไหน &quot;ใช้ได้&quot; มาไว้อีกที่หนึ่ง (ADR-066)
          </p>
        </details>
      )}

      <h1>2 · เกณฑ์ของกฎตรวจจับ</h1>
      {proposed.length === 0 ? (
        <p className="card">ยังไม่มีข้อเสนอเรื่องเกณฑ์ — เหตุผลของแต่ละกฎอยู่ข้างล่าง</p>
      ) : (
        proposed.map((line) => {
          const one = line.proposal!;
          return (
            <article className="card" key={line.rule_id}>
              <div className="screen-head">
                <h2>{line.rule_id}</h2>
                <span className="muted">
                  {one.current_threshold} → {one.proposed_threshold}
                </span>
              </div>
              <p className="reason">{one.reason}</p>
              <p className="muted">
                จาก {one.observations} ใบ · แจ้งเท็จ {one.false_alarms} ใบ · พบของจริง{" "}
                {one.faults_found} ใบ
                {one.excluded_predictions > 0 &&
                  ` · ตัด Finding แบบ predicted ออก ${one.excluded_predictions} ใบ`}
                {line.without_a_reading > 0 &&
                  ` · ไม่มีค่าที่อ่านได้ ${line.without_a_reading} ใบ`}
              </p>
              {one.capped && (
                <p className="warning">
                  หลักฐานแยกกันที่ {one.separating_threshold} แต่หนึ่งรอบขยับได้ไม่เกิน 10%
                  (ADR-073)
                </p>
              )}
              <p className="warning">{one.limitation}</p>
              <p className="muted">
                จะใช้ค่านี้: แก้ <code>config/rules.yaml</code> ด้วยมือ — ที่ <code>{line.rule_id}</code>{" "}
                เปลี่ยน <code>threshold: {one.current_threshold}</code> เป็น{" "}
                <code>threshold: {one.proposed_threshold}</code> แล้ว restart
                ระบบไม่มีทางแก้ไฟล์นี้ให้เอง และไม่ควรมี: ไฟล์นี้คือสิ่งที่ layer 1 บูตขึ้นมาอ่าน
                และการแก้ต้องผ่านรีวิวเหมือนโค้ด (ADR-087)
              </p>
            </article>
          );
        })
      )}
      {refused.map((line) => (
        <article className="card" key={line.rule_id}>
          <div className="screen-head">
            <h2>{line.rule_id}</h2>
            <span className="pending">{causeName(line)}</span>
          </div>
          <p className="muted">
            {line.metric_name} · ยิงเมื่อ{line.comparison === "above" ? "เกิน" : "ต่ำกว่า"}{" "}
            {line.current_threshold}
          </p>
          <p className={line.safety_critical ? "warning" : "reason"}>{line.refusal!.reason}</p>
        </article>
      ))}
    </>
  );
}

/**
 * The refusal, in a phrase a person can group by.
 *
 * The English cause is what the API sends and what the reason sentence explains;
 * this is only the label on the row. A cause this list has not heard of is shown
 * as itself rather than as "อื่น ๆ", so a new refusal in `work/thresholds.py`
 * arrives on screen readable instead of silently collapsing into a bucket.
 */
function causeName(line: ThresholdLine): string {
  switch (line.refusal!.cause) {
    case "safety_critical":
      return "เกี่ยวกับความปลอดภัย · ห้ามเสนอผ่อนเกณฑ์";
    case "below_floor":
      return `ยังไม่ถึงเกณฑ์ขั้นต่ำ · ${line.refusal!.observations} ใบ`;
    case "no_false_alarms":
      return "ไม่มีการแจ้งเท็จ";
    case "no_confirmed_fault":
      return "ยังไม่เคยพบของจริง";
    case "no_separating_threshold":
      return "ไม่มีเกณฑ์ไหนแยกได้";
    case "cap_excludes_nothing":
      return "รอบนี้ขยับได้ไม่พอ";
    default:
      return line.refusal!.cause;
  }
}

# IS: ระบบคาดการณ์ซ่อมบำรุงและออก Ticket อัตโนมัติ

## บริบทโปรเจกต์

Individual Study ระยะเวลา 1 เทอม ของนักศึกษา CEDT ปี 2 จุฬาลงกรณ์มหาวิทยาลัย
ทำร่วมกับอาจารย์ผู้สอนวิชาระบบฝังตัว โจทย์มาจากโรงงานประกอบรถยนต์ Ford
จังหวัดระยอง ซึ่งกำลังขยับไปสู่ full automation (ปัจจุบันบางไลน์เป็นอัตโนมัติแล้ว)

รายละเอียดบทสนทนากับอาจารย์ทั้งหมดอยู่ที่ `docs-md/professor_notes.md`
แผนงานเต็มและตารางเปรียบเทียบทางเลือกอยู่ที่ `docs-md/plan.md`
เหตุผลเบื้องหลังการตัดสินใจแต่ละข้ออยู่ที่ `docs-md/decision.md`
รูปทรงระบบ โมดูล และกฎการพึ่งพาอยู่ที่ `docs-md/design.md`
หน้าจอและเหตุผลเบื้องหลังอยู่ที่ `docs-md/ui.md`
กลไกที่ทำให้ระบบดีขึ้นตามเวลาอยู่ที่ `docs-md/feedback_loops.md`
วิธีทำงานและการใช้ AI กับโปรเจกต์นี้อยู่ที่ `docs-md/workflow.md`
กฎ git workflow, รูปแบบ commit/PR และ CI/CD อยู่ที่ `docs-md/git.md`
บทเรียนที่ขนมาจากงานเดิม (และเส้นที่ห้ามข้าม) อยู่ที่ `docs-md/lessons_carried.md`

## เป้าหมายเดียวที่ต้องยึด

> ปลายเทอมต้องมีระบบที่ช่างคนหนึ่งเปิดขึ้นมาแล้วทำงานตามได้จริง
> แม้ข้อมูล sensor จาก Ford จะไม่เคยมาถึงเลย

ทุกการตัดสินใจเอาประโยคนี้ไปวัด ถ้าอะไรไม่รับใช้ประโยคนี้ ให้เลื่อนเป็น future work

สองข้อที่ตามมาจากประโยคนี้ และห้ามปล่อยให้กลายเป็นงานสำรอง:

- **"ช่างคนหนึ่ง" ต้องมีตัวจริง** — หาช่างซ่อมบำรุงมาลองใช้ให้ได้ 1 คน
  เป็นงานที่เราต้องผลักดันเอง ไม่ผูกกับการที่ข้อมูล sensor จะมาหรือไม่มา
- **รายงานผ่าน MCV คือชิ้นงานที่ถูกให้เกรด** — กันสัปดาห์ 13–14 ไว้เขียน
  ทุกกรณี ไม่ว่าข้อมูลจะมาหรือไม่

## สถาปัตยกรรม 4 ชั้น

```
แหล่งงาน 3 ทาง
 ├── สัญญาณเครื่องจักร (SignalSource) → ชั้น 1 · Trigger      [ทำบน synthetic ได้เลย]
 │      ตรวจจับ: rule + threshold          → Finding (detected)
 │      คาดการณ์: trend → เวลาถึงเกณฑ์      → Finding (predicted + ETA)
 ├── ตาราง PM ตามรอบ → งาน priority รอง (origin = scheduled)   [เริ่มได้ทันที]
 └── ช่าง/หัวหน้ากะแจ้งเอง (origin = manual)                   [เริ่มได้ทันที]
                    │
                    ▼
ชั้น 2 · Content — ประกอบ ticket พร้อมวิธีซ่อมจาก playbook      [เริ่มได้ทันที]
        │                    ▲
        │                    └── คลัง playbook (สร้างจากคู่มือด้วย RAG)
        ▼
ชั้น 3 · Dispatch — จัดคิวตาม priority × โหลดของกะ              [เริ่มได้ทันที]
        │                    ▲
        │                    └── ข้อมูลช่าง (ทักษะ ตารางกะ งานค้าง)
        ▼
ชั้น 4 · ระบบปลายทาง — ticket ไปโผล่ที่ไหน                      [รอคำตอบอาจารย์]
        │      CMMS เดิม (SAP PM / Maximo) หรือระบบของเราเอง หรือ LINE / Teams
        ▼
      ช่าง — รับงาน ปิดงาน แก้ไขขั้นตอน → ป้อนกลับเข้าคลัง playbook
```

**หลักการสำคัญ:** ชั้น 2 และ 3 ต้องไม่บล็อกรอชั้น 1 ทุกชั้นแยกพัฒนาได้

**ชั้น 1 ไม่ได้รอข้อมูลจริง** — อาจารย์เปิดโจทย์ด้วยคำว่า "ตรวจสอบ**และคาดการณ์**"
ซึ่งเป็นข้อกำหนดข้อแรก จึงต้องส่งให้ได้ทั้งสองอย่าง ไม่ใช่แค่ตรวจจับ
`SyntheticSource` จำลองความเสื่อมโดยรู้เวลาเสียจริงตั้งแต่ตอนสร้างข้อมูล
เท่ากับมี label ให้วัดความแม่นของการคาดการณ์ได้ทันทีโดยไม่ต้องรอโรงงาน (ADR-020)

**ชั้น 4 คือชั้นที่เสี่ยงที่สุด** เพราะคำตอบเรื่อง CMMS เปลี่ยนสถาปัตยกรรมทั้งหมด
ต้องถามอาจารย์ให้ได้คำตอบเร็วที่สุด — ระหว่างยังไม่รู้ ให้เขียน ticket ออกทาง
interface ที่มี adapter สลับได้ ไม่ผูกกับปลายทางใดปลายทางเดียว

## หลักการที่ห้ามละเมิด

1. **Runtime ต้อง deterministic** — ไม่ให้ LLM แต่งคำสั่งซ่อมสด ๆ ตอนใช้งาน
   เพราะเป็นงาน safety-critical ค่า torque หรือลำดับ lockout ที่ผิดคือความเสี่ยงต่อคน
   LLM ทำงานที่ build time (ร่าง playbook) ไม่ใช่ runtime
2. **ทุก playbook ต้องมี traceability** — `source_doc` + `page` (รายขั้น) +
   `revision` + `approved_by` + `approved_at` ครบทุกใบ ไม่มีใบไหนถึงมือช่าง
   โดยไม่มีคนอนุมัติ และใบงานที่ปิดแล้วต้องพิสูจน์ได้ว่าตอนนั้นสั่งอะไร
   ผ่าน `playbook_snapshot`
3. **ทุก ticket ต้องอธิบายได้** — ต้องบอกช่างได้ว่าทำไมงานนี้ถูกจัดให้เขา
   และทำไมมาก่อนงานอื่น ถ้าอธิบายไม่ได้ ช่างจะเลิกใช้ระบบ
4. **ไม่มีอะไรบล็อกรอข้อมูลจากโรงงาน** — ทุกส่วนต้องทดสอบได้ด้วย synthetic data
5. **เมื่อหลักฐานไม่พอ ให้ระบบยอมรับว่าไม่รู้** — แสดง "ไม่พบข้อมูล ดูคู่มือหน้า X
   หรือติดต่อวิศวกร" ดีกว่าเดา

## สัญญาข้อมูล (Data Contracts)

สัญญาทั้งหมดมีแปดตัว **ต้องนิ่งก่อนเขียนโค้ดส่วนอื่น** เพราะทุกส่วนต่อกันผ่านของพวกนี้

- **สี่ตัวที่อธิบายงาน** — อยู่ในไฟล์นี้ เพราะแตะแทบทุกครั้งที่เขียนโค้ด
  `Signal` → `Finding` → `Playbook` → `WorkOrder`
- **สี่ตัวที่อธิบายทรัพยากรและสถานที่** — อยู่ที่ `docs-md/design.md` หัวข้อ 13
  `Station`/`Line` · `Skill` · `Technician`/`Shift` · `PMTask` (ADR-027)
  ชั้น 3 ใช้ทั้งสี่ตัว ถ้าจะแตะ `dispatch/` หรือ `load_ratio` ต้องเปิดอ่านก่อน

และมีของอีกสองอย่างที่ไม่ใช่สัญญาข้อมูลแต่ต้องมีก่อนโค้ดบรรทัดแรก —
`Clock` port (ADR-028) และกฎ import + gate ใน CI (ADR-029)
ดู `docs-md/design.md` หัวข้อ 11 ลำดับ 0

### Signal
```
timestamp, machine_id, metric_name, value, unit
```
หน้าตาเดียวไม่ว่ามาจาก synthetic generator, ไฟล์ replay, หรือ OPC UA จริง

### Finding
```
machine_id, component, symptom_code, severity, evidence, detected_at,
kind, eta, eta_confidence,
rule_id, status, occurrence_count, last_seen_at, superseded_by
```
`evidence` ต้องเก็บว่าอะไรทำให้เตือน (ค่าอะไร เกินเกณฑ์เท่าไร นานแค่ไหน)
เพื่อให้อธิบายช่างได้

`status` มีค่า open / acknowledged / resolved / expired / superseded

**rule ที่ยิงซ้ำต้องอัปเดตใบเดิม ไม่สร้างใบใหม่** — คีย์กดทับคือ
(`machine_id`, `rule_id`) ตราบใดที่ยังมีใบ open/acknowledged อยู่
การยิงซ้ำแค่เพิ่ม `occurrence_count` และขยับ `last_seen_at`

ถ้าไม่มีข้อนี้ มอเตอร์ร้อนเกินหนึ่งตัวจะสร้าง Finding ทุกรอบการอ่านค่า
กลายเป็น WorkOrder ร้อยใบ แล้ว `load_ratio` พุ่งจนเกิน 100% แล้ว load gate
กลั้นทุกอย่าง — ระบบทำลายตัวเองภายในชั่วโมงแรกที่รันจริง ดู ADR-023

`kind` มีค่า **detected** (ค่าเกินเกณฑ์แล้ว) หรือ **predicted** (แนวโน้มชี้ว่า
จะถึงเกณฑ์) — ใบ predicted ต้องมี `eta` และ `eta_confidence` เสมอ และ
`priority_reason` ของ WorkOrder ต้องพูดต่างกันสองแบบ ("เกินเกณฑ์แล้ว 20 นาที"
กับ "คาดว่าจะถึงเกณฑ์ในอีก ~6 ชั่วโมง ± 2") เพราะช่างตัดสินใจต่างกัน
งาน predicted คือสิ่งที่ควรถูกดึงเข้ามาทำตอนโหลดเบา ดู ADR-020

`component` **ไม่ได้มาจากการอนุมาน** — rule แต่ละข้อประกาศไว้ในนิยามของตัวเองว่า
เฝ้า component ไหน (สัญญาณหนึ่ง tag ผูกกับ component หนึ่ง) rule ที่ระบุไม่ได้
เช่นสัญญาณระดับไลน์ ให้ใส่ `component = unknown` แล้วชั้น 2 ต้องเสิร์ฟ playbook
ประเภทช่วยไล่หาจุด ไม่ใช่ playbook ซ่อม — นี่คือคำตอบของข้อกำหนด "ซ่อมจุดไหน"
ดู ADR-009

### Playbook
```
symptom_code, machine_model, steps[], tools[], parts[],
estimated_minutes, required_skill, required_technicians,
source_doc, page, revision, approved_by, approved_at, approver_role, status
```
```
steps[] แต่ละขั้น = { text, source_doc, page, confidence }
```
`status` มีค่า draft / approved / needs_review

**หนึ่งแถวต่อหนึ่ง (`symptom_code`, `machine_model`)** ไม่มีสายเวอร์ชัน
ไม่มี `supersedes` การอนุมัติเขียนทับใบเดิมและเพิ่ม `revision` ขึ้นหนึ่ง
ประวัติไม่ได้อยู่ที่นี่ แต่อยู่ใน `playbook_snapshot` ของ WorkOrder (ADR-018)

**ทุกขั้นตอนถือที่มาของตัวเอง** ไม่ใช่มี `source_doc`/`page` แค่ระดับใบ
เพราะ authoring ตั้งค่าให้ recall กว้าง (ADR-015) โอกาสที่ LLM ร่างใบซึ่ง
ผสมขั้นตอนจากคนละเอกสารจึงสูงขึ้น ถ้าที่มาอยู่ระดับใบ ใบที่ผสมกันจะดูเหมือน
ใบปกติ แต่ถ้าอยู่ระดับขั้น ใบผสมจะฟ้องตัวเองว่ามีขั้นที่อ้างคนละเอกสาร
ระดับใบยังเก็บไว้ในฐานะเอกสารหลักของใบนั้น

เมื่อ operator เปลี่ยนคู่มือ playbook ทุกใบที่มาจากเล่มนั้นเด้งเป็น
`needs_review` ยังเสิร์ฟต่อพร้อมป้ายเตือนจนกว่าจะอนุมัติใหม่
ลำดับการเสิร์ฟตอน runtime อยู่ใน `docs-md/plan.md` หัวข้อชั้น 2

`required_technicians` มีค่าตั้งต้น 1 — งานที่ต้องสองคน (เช่นถอดมอเตอร์หนัก)
กิน capacity ของกะเป็นสองเท่า ถ้าไม่มีฟิลด์นี้ `load_ratio` จะนับต่ำกว่าจริง
แล้ว scheduler จะแจกงานเกินกำลังคน ดู ADR-025

`approver_role` บันทึกบทบาทที่ผู้อนุมัติ **ถืออยู่ ณ เวลาที่กด** ไม่ใช่บทบาท
ปัจจุบัน — บทบาทเปลี่ยนได้ แต่หลักฐานการอนุมัติต้องสะท้อนสภาพตอนนั้น
หลักคิดเดียวกับ `playbook_snapshot` ดู ADR-024

### WorkOrder
```
origin, finding_ref?, pm_task_ref?, playbook_ref, playbook_snapshot,
machine_id, severity, finding_kind?, eta?, eta_confidence?,
priority_score, priority_reason, status,
assignees[], work_segments[], handover_note,
actual_minutes, blocked_minutes, blocked_reason, outcome, technician_feedback
```
```
assignees[]     = [{ user, role: primary | helper }]
work_segments[] = [{ user, started_at, ended_at }]
```
**บรรทัดที่สองคือข้อเท็จจริงที่ scheduler ต้องใช้ ซึ่งใบงานถือไว้เอง**
`work/` คัดลอกลงใบงาน ณ เวลาสร้าง แล้ว `dispatch/` **ไม่อ่าน `Finding` เลย**
— ถ้าไม่มีข้อนี้ `dispatch/` จะคำนวณ `w2` (ต้องใช้ `machine_id` → สถานี)
และ `w5` (ต้องใช้ `eta`) ไม่ได้โดยไม่ละเมิดกฎ "ห้าม import `triggers/`"
ของตัวเอง แบบแผนเดียวกับ `playbook_snapshot` คือคัดลอกสิ่งที่ต้องใช้
มาไว้ที่ที่ต้องใช้มัน ดู ADR-030

`severity` อยู่ที่ใบงานไม่ใช่ที่ `Finding` เพราะงาน `scheduled` และ `manual`
ไม่มี Finding ผูก ถ้า severity อยู่ฝั่งโน้น load gate ที่ ADR-011 บอกว่า
"ผ่านเฉพาะ severity สูง" จะตัดสินงานสองประเภทนั้นไม่ได้เลย

`finding_ref` มีไว้ **สืบกลับ** ไม่ใช่ให้ scheduler ดึงข้อมูล — UI ของช่าง
ที่ต้องแสดง "เกิดซ้ำ N ครั้ง" อ่านผ่าน `finding_ref` เพราะค่าที่คัดลอกลงใบงาน
เป็นภาพนิ่ง ณ เวลาสร้าง และตั้งใจให้ไม่ขยับตาม (`design.md` 6.2)
`actual_minutes` = **ผลรวมของ `work_segments` ไม่ใช่ (เวลาปิด − เวลาเริ่ม)**
เพราะงานหนึ่งใบอาจข้ามกะ ถูกวางแล้วกลับมาทำต่อ หรือมีคนช่วยหลายคน
และ `blocked_minutes` (รออะไหล่ รอไลน์หยุด) ต้องหักออกก่อนป้อนกลับเข้า
`estimated_minutes` ไม่งั้นค่าประมาณจะพองทุกรอบ ดู ADR-025
`playbook_snapshot` คือสำเนาแช่แข็งของ `steps[]` + ที่มารายขั้น +
`approved_by` / `approved_at` **ณ เวลาที่ออกใบงาน** ห้ามแก้ตลอดอายุใบ

**นี่คือของที่ทำให้ตัดสายเวอร์ชันออกได้อย่างปลอดภัย** — ใบงานที่ปิดไปแล้ว
ต้องพิสูจน์ได้ว่าตอนนั้นระบบสั่งอะไร ถ้าประวัติอยู่ที่ตาราง playbook
การเขียนทับจะทำให้ใบงานเก่าชี้ไปยังขั้นตอนที่ไม่ใช่สิ่งที่ช่างทำจริง
พอย้ายประวัติมาไว้ที่ที่ต้องใช้มัน ตาราง playbook ก็เขียนทับได้อิสระ (ADR-018)
`origin` มีค่า condition (มาจาก Finding) / scheduled (PM ตามรอบ) /
manual (คนแจ้ง) — `finding_ref` จึงเป็น optional เพราะงาน priority รอง
ที่อาจารย์สั่งให้แจกตอนโหลดเบา ส่วนใหญ่ไม่มี Finding ผูก ดู ADR-010

**หมายเหตุสำคัญ:** `estimated_minutes` (ใน Playbook) กับ `actual_minutes`
(ใน WorkOrder) ต่างกันโดยเจตนา ตัวแรกคือค่าที่ scheduler ใช้คำนวณ ตัวหลังคือ
ข้อมูลจริงที่เอามาปรับค่าประมาณให้แม่นขึ้น — นี่คือ feedback loop ที่ทำให้ระบบ
ดีขึ้นโดยไม่ต้องใช้ ML

## Technology Stack

เหตุผลการเลือกทั้งชุดอยู่ที่ ADR-008 — ห้ามเพิ่ม dependency ใหม่โดยไม่มี ADR

- **Backend:** Python, FastAPI, PostgreSQL
- **Retrieval:** Qdrant (dense), PostgreSQL full-text (sparse), reciprocal rank fusion,
  cross-encoder reranking — สถาปัตยกรรมเดียวกับที่ผู้ทำเคยส่งขึ้น production ที่ CPF
- **Job queue:** ตาราง job ใน PostgreSQL (`FOR UPDATE SKIP LOCKED` + heartbeat
  + reaper) ไม่มี Redis — enqueue/complete commit พร้อมข้อมูลจริงในทรานแซกชัน
  เดียว จึงไม่มีทางเกิด playbook ที่ไม่มี job ผูก หรือกลับกัน (ADR-017)
- **Optimization:** OR-Tools (CP-SAT) สำหรับ scheduler
- **Simulation:** SimPy หรือ discrete-event simulator เขียนเอง
- **Frontend:** Next.js
- **Deployment:** Docker, on-premise (ข้อมูลโรงงานติด NDA ห้ามขึ้นคลาวด์)
  7 container โดย `api` / `worker-runtime` / `worker-authoring` มาจาก image
  เดียวกัน และ `llm-server` อยู่บน network ที่ `api` เข้าไม่ถึง
  (ADR-026, ADR-029 · `docs-md/design.md` 1 และ 15)

## พื้นฐานของผู้ทำ

เคยสร้างและส่งมอบระบบ RAG on-premise ให้โรงงาน CPF (ระบบชื่อ Neo Chat)
ตอบคำถามวิศวกรโรงงานเป็นไทย/อังกฤษจากคู่มือหุ่นยนต์ I/O mapping และแบบไฟฟ้าสแกน
รันบน NVIDIA Jetson AGX Orin บน LAN โรงงาน — จุดที่นำมาใช้ต่อได้โดยตรง:

- Hybrid retrieval ข้ามภาษา (คำถามไทย เอกสารอังกฤษ) — คู่มือ Ford ก็จะเป็นอังกฤษ
- NLI entailment gate + self-verification + extractive fallback กัน fabrication
- Vision-language ingestion อ่านแบบไฟฟ้าสแกนเป็นตาราง device/connection
- ประสบการณ์ที่ฟีเจอร์ predictive maintenance ถูกถอดออกเพราะไม่มี sensor data
  และไม่มี failure label — บทเรียนที่กำหนดรูปร่างของโปรเจกต์นี้

## การสื่อสาร

- ตอบเป็นภาษาไทย ศัพท์เทคนิคใช้ภาษาอังกฤษตามเดิม
- ก่อนทำงานก้อนใหญ่ ให้เสนอแผนก่อน อย่าเพิ่งแก้ไฟล์
- เมื่อตัดสินใจเชิงสถาปัตยกรรม ให้บันทึกเหตุผลลง `docs-md/decision.md`
  โดยเพิ่ม ADR ใหม่ต่อท้าย ไม่แก้ทับของเก่า ถ้าเปลี่ยนใจให้เขียนใบใหม่ที่อ้างของเดิม
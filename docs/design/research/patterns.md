# Patterns to steal: research for the frontend redesign

Every feature claim cites a URL I read. "Unverified" = not confirmed from a primary or near-primary source. Help pages describe behaviour, not pixels.

## 0. What we are replacing (`/home/claude/ui/png/before`, `v3`)

SaaS-template look: blue app bar, rounded cards, pills, coloured left borders, emoji icons. The current step fills ~40% of the first phone viewport, the full list repeats below it, and the tab bar overlaps content. The board has 4 kanban columns (3 near-empty), paragraph-long cards and 3 differently styled actions. Owner-trial layout defects: a frozen relative time beside a live clock, a pill overflowing its column, lost reports, no confirmation after actions.

---

## 1. Mobile CMMS / work-order apps

### MaintainX
Steal:
- **Typed procedure fields**: Number, Multiple Choice, **Inspection Check (Pass / Flag / Fail; Flag or Fail prompts corrective action)**, Yes/No/N/A, Photo, Signature, Meter Reading. Each can be **Required**, conditional on another field, and carry a **manual link** and reference photo. https://help.getmaintainx.com/procedure-fields
- **Four statuses**: Open, On Hold, In Progress (set automatically on the first step update), Done. Timer: Start / Pause / Resume / Stop. https://help.getmaintainx.com/complete-a-work-order
- **Capacity vs workload per technician** in the scheduler ("visualize capacity at a glance", shifts and time off per person). https://www.getmaintainx.com/use-cases/resource-planning
Avoid: AI-generated procedures/estimates (https://www.getmaintainx.com/llms.txt), which conflict with approved-only steps; cost/rate fields on close.

### UpKeep
Steal:
- **Offline caching of the technician's own work.** Assigned work orders, work orders on non-operational assets and those due this week are cached. Checklists can be finished offline (values, notes, photos), and edits sync automatically on reconnect. https://help.onupkeep.com/en/articles/4712557-how-to-use-upkeep-offline
- Task items save as soon as a value is entered, with no separate save button. https://help.onupkeep.com/en/articles/9339534-how-to-view-and-process-your-work-order
Avoid: no documented pending-sync indicator, so users cannot see what has not reached the server.

### Fiix (Rockwell)
Steal:
- **Failure codes in three parts: problem, cause, action**, entered on mobile under Details > Failure codes. https://helpdesk.fiixsoftware.com/hc/en-us/articles/4413567990932-Assign-failure-codes-to-work-orders
- **Warning when closing with open tasks**: Cancel (finish the tasks) or Yes (close anyway). https://helpdesk.fiixsoftware.com/hc/en-us/articles/4413544570004-Close-a-work-order-mobile
Avoid: closing via a status dropdown, which makes the key action look like a form edit.

### Limble
Steal:
- **An asset QR code that opens a work-request form with the asset already filled in**, plus a second code for asset information. https://help.limblecmms.com/en/articles/3637230-qr-code-overview . Request portal: https://help.limblecmms.com/en/articles/6801095-how-to-set-up-a-work-request-portal
Unverified: Limble's mobile LOTO, checklist and offline UI.

### eMaint (Fluke)
Unverified: marketing pages only (https://www.emaint.com/mobile). Nothing taken.

### SAP Service and Asset Manager (SAP PM mobile)
Steal:
- **An isolation point is its own object**, with status **Tagged / Untagged**, the **physical lock number**, a **signature for the tagging action** and **photos at tag and untag**. Permits and safety certificates show approval status and an isolation-point list. https://community.sap.com/t5/enterprise-resource-planning-blogs-by-sap/safety-technician-persona-in-sap-service-and-asset-manager/ba-p/13565634
- Offline execution, mobile time confirmation, and LOTO "physical locks and tags that de-energize equipment". https://www.sap.com/products/scm/asset-manager/features.html
Avoid: safety measures at order level only (release 2305). Ours attach to the step.

### IBM Maximo Mobile
Steal:
- **"My Schedule" lists assigned work in priority order** and offers a list or map view. **Start Work** starts the labour clock. **Report Work** records **Failure Class > Problem > Cause > Remedy** and materials. **Complete work** closes. https://ibm.github.io/maximo-labs/mas_9.0/demo-mobile-assist
- **Accept / Reject before start.** Reject takes a reason from a "Reasons for rejection" list, and after Accept the control changes to the Start/Stop timer. Rejected work drops out of the technician's list and planners query it. https://maxlogic.substack.com/p/accept-reject-work-assignments-with
Avoid: an icon-only toolbar (lab above). Gloved, Thai-first users need labels.

---

## 2. Connected-worker / digital work instructions

### Dozuki (and iFixit, the same guide engine)
Steal:
- **Operator View: one step per full screen, Next Step bottom-right**, data form in a right column, **Pause** for break/handover, confirmed Cancel, target time beside the running timer. https://dozuki.dozuki.com/c/Operator_View
- **Step sign-off** (self, or team in person / remote via "Pending Signoffs"); a finished run yields a PDF summary. https://dozuki.dozuki.com/Answers/View/65663/Checklists+and+Forms+Best+Practices
- **Typed bullets**: instruction (default), **Note** (context), **Reminder** ("make sure" checks), **Caution** (bodily harm or irreversible; "use caution bullets sparingly!"). Colour a bullet only to match a photo marker. https://help.dozuki.com/Guide/How+to+Use+and+Think+About+Bullets/6792
- **At most 3 images per step.** https://www.ifixit.com/Help/Guide_Steps
Avoid: leaving a step before Next loses its data. Ours autosave.

### Tulip
Steal:
- **"Primary action buttons should be the boldest color on the screen."** Standardise layouts, colours and button shapes across all apps. https://support.tulip.co/docs/app-design-best-practices
- **Next action bottom-right**, where the hand already is. **Alerts bold and big enough for peripheral vision** (audio is lost in noise). **Bolder text for goggle/face-shield users.** **Friction only on dangerous actions.** https://tulip.co/blog/designing-software-with-intention-how-to-optimize-frontline-operator-processes/
- Targets > 44×44 px; text ≥ 13 pt "but consider going larger"; split cluttered steps; test under real lighting and while walking. https://community.tulip.co/t/mobile-ui-ux-best-practices/6821

### Augmentir
- Steal **skill gating**: skills are "integrated into digital work instructions to assure that only qualified people are able to execute work"; Smart Forms validate and branch. https://www.augmentir.ai/product
- Unverified: step layout, photo capture, offline. Avoid its AI-personalized instructions.

---

## 3. Industrial HMI guidance

### ISA-101 / high-performance HMI
Steal:
- **"Gray is good"**: a mostly grey, monochrome screen, so that colour means something is wrong. https://control.com/technical-articles/going-gray/
- **Bright colour only for abnormal states. Never use colour alone. Reserve alarm colours for alarms. No red/green run/stop coding**: show state with brightness and a status word. **Encode alarm priority redundantly with shape + colour + text.** https://blog.isa.org/the-high-performance-hmi
- **Display hierarchy**: L1 area overview (KPIs, **no control actions**), L2 unit (main working screen), L3 equipment (diagnosis), L4 diagnostic detail (same source).
- **Embedded trends that show the desirable range**, not trend-on-demand. **Analog indicators show the normal band and the distance to alarm and interlock limits.** The goal is to judge "out of range, by how much, how close to limits" in **one 2-second glance** (same source).
- A secondary source states that ISA-101.01 requires state and priority to be encoded in at least two of the three channels (colour, shape, text), and that the colours themselves are not specified. It gives a common mapping: P1 red, P2 amber, P3 yellow, P4 blue/cyan. Its other specs: a deviation pointer that is grey inside the band, amber near the edge and red at the limit; and a sparkline of 60-120 × 15-30 px with no axes. https://industrialmonitordirect.com/blogs/knowledgebase/isa-101-high-performance-hmi-design-principles-color-strategy (secondary; I could not read the ISA text)
Avoid: "ISA-101" vendor palettes that colour running green and reuse one yellow for alarm and transition (https://docs.tatsoft.com/display/FX/ISA-101+HMI+Compliance+How-to).

### ASM Consortium
Steal:
- **A salience hierarchy**: top-priority alarms most prominent, equipment IDs least (for us: Thai machine name first, `MC-012` secondary). **Overview displays are mandatory, and trends often work best as the overview. Use a shape library for consistency.** Prototype one display of each type and review it with operators from every shift. Test colours on the real hardware under real lighting. https://process.honeywell.com/content/dam/process/en/documents/document-lists/doc_asm-consortium/white-papers/October%201%202008%20-%20Operator%20Effectiveness%20by%20Design.pdf

### NAMUR NE 107 (device diagnostics)
Steal the vocabulary for machine/sensor health, kept separate from job priority. NE 107 has four statuses: **Failure**, **Out of specification**, **Maintenance required** and **Check function**. "Check function" covers a sensor that is temporarily unreliable, which fits synthetic or imported data that is stale. https://www.us.endress.com/en/support-overview/learning-center/namur-ne-107 . The official icons and colours were not readable (they are in an image), so they are unverified.

---

## 4. Safety communication

- **ISO 3864 colours**, from a secondary transcription (I could not read the ISO text): red #9B2423 = prohibition, white contrast; yellow #F9A900 = warning, black contrast; blue #005387 = mandatory, white; green #237F52 = safe condition, white. https://en.wikipedia.org/wiki/ISO_3864 . Meanings are fixed, so our UI must not reuse these hues for unrelated things (for example blue for links next to a blue mandatory sign).
- **ISO 7010 symbols that fit our steps**: W012 electricity, W017 hot surface, W018 automatic start-up, W019/W024 crushing, M021 disconnect before maintenance, M001 general mandatory (with text), P031 do not alter the state of the switch. https://en.wikipedia.org/wiki/ISO_7010 . **Licensing of the ISO artwork is unverified.** Draw our own SVG following ISO 3864 geometry, or ask the plant for its sign set.
- **ANSI Z535 signal words**: DANGER = "will result in death or serious injury" (red); WARNING = "could result in death or serious injury" (orange); CAUTION = minor or moderate injury (yellow); NOTICE = property damage only, never with the alert triangle. https://www.safetysign.com/safety-header
- **OSHA 1910.145 tags**: "a signal word and a major message" (example: "Do Not Start"), and the signal word must be understandable to all exposed employees. https://www.law.cornell.edu/cfr/text/29/1910.145 . For us, Thai comes first.
- **OSHA 1910.147** is the structure our isolation step must follow. https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147
  - Content ((c)(4)(ii)): intended use; shutdown/isolate/block/secure steps; placing, removing, transferring locks and tags; **the test that verifies isolation**.
  - **Order** ((d)): (1) know energy type and magnitude; (2) orderly shutdown; (3) operate **every** isolating device; (4) lock/tag each; (5) relieve stored energy; (6) **verify isolation before work**.
  - Release ((e)): area clear and equipment intact; all people accounted for; notify affected employees; **each lock removed by whoever applied it**.
- **Data gap.** `Step` (`web/lib/work.ts`) has only `text`, `text_th`, `source_doc`, `page`, `manual`: no energy, isolation-point or hazard fields. The UI must not invent them; marking a step as isolation needs a backend flag (v3's banner had none).

---

## 5. Shift-lead dispatch boards

- **Palmer**: "Field supervisors take care of daily scheduling"; a **credible priority system with "more than three simple levels"**; bundle low-priority jobs on the same asset/area; plans state the **craft skill**. https://www.plantservices.com/voices/palmers-planning-corner/article/55361071/do-you-know-the-purpose-and-principles-of-maintenance-planning-and-scheduling
- **Andon**: a grid with one cell per line or station, built around "a few key pieces of critical information". Red = line stopped, act now; yellow = issue, line still running; green = OK; blue = planned stop. "Colour conventions may differ by region." https://vorne.com/learn/key-concepts/andon
- **Salesforce Field Service console**: appointment list filterable to **"In Jeopardy"**/unscheduled, a **Gantt** with **rule violations as a yellow triangle**, "Get candidates" for qualified workers, emergencies show displaced jobs. https://trailhead.salesforce.com/content/learn/modules/field-service-dispatcher-console-for-dispatchers/manage-service-appointments , https://trailhead.salesforce.com/content/learn/modules/field-service-dispatcher-console-for-dispatchers/handle-the-unexpected
- **Gantt vs kanban vs table** (one shift, 3-6 technicians): a priority-sorted **table** for the decision queue (one column to scan); **swimlanes** (row per technician, shift time axis) for overload/idle; **no status kanban**, which wastes width when columns are empty (our `sup_board.desk.png`) and hides priority across columns.

---

## 6. Thai UI typography

- Material classes Thai as a **"tall" script that "require[s] extra line height"** but gives no number. https://zavoloklom.dev/material-design-typography/ (mirror of Material language guidance). Thai needs "more interline spacing" than Latin, and marks go both above and below the base. https://r12a.github.io/scripts/tutorial/summaries/thai
- **Up to four stacked mark levels above the base** (ABOVE1 vowel, ABOVE2, ABOVE3 tone, ABOVE4 thanthakhat). https://learn.microsoft.com/en-us/typography/script-development/thai . Any container with fixed height or `overflow:hidden` risks clipping, so test with strings such as "ปั๊ม ญี่ปุ่น ฎีกา ฐาน กิ๊ก".
- **No spaces between words.** Line breaking needs dictionary lookup (r12a). **Browsers fail Thai justification, and letter-spacing adds a trailing gap.** https://www.w3.org/TR/2021/WD-thai-gap-20210525/ → No `text-align: justify` and no letter-spacing on Thai.
- **Use looped (headed) Thai for reading text.** Loopless "Roman-like" Thai at small sizes "harms legibility and readability", and some letters are misread as Latin (พ/w, ร/s, บ/U). https://so04.tci-thaijo.org/index.php/abc/article/download/54148/44944/125343 (Punsongserm 2012). IBM Plex Thai's looped style is "more familiar to older readers", and the family "perform[s] exceptionally well at small sizes". https://www.fontpad.co.uk/?p=1772 . Loopless reads as modern and branded, looped as formal (https://www.fontpad.co.uk/?p=666).
- **Regular weight is the most legible Thai screen style.** Italic, condensed, bold and outline all scored lower (n=90). https://digital.car.chula.ac.th/chulaetd/23553 → No italic Thai, and bold only for one phrase.
- **Size**: a 2025 survey of Thai government apps found most body text above **1.2 mm** Bo Baimai height and most regular text **failing 7:1**. https://jged.uns.ac.rs/index.php/jged/article/view/1594 (descriptive, not a standard).
- **Fonts**: IBM Plex Sans Thai Looped for body, IBM Plex Sans Thai (loopless) only for large headings or not at all, and Plex Sans / Plex Mono for codes and figures. Alternative: Noto Sans Thai Looped. **Self-host all fonts**, because the plant may have no internet. Plex/Noto licences are believed to be OFL; verify before shipping.

---

## 7. Gloves, glare, one hand

- **Target size**:
  - NN/g: at least **1 × 1 cm**. Fingertips are 1.6-2 cm wide and the thumb contact area about 2.5 cm. https://www.nngroup.com/articles/touch-target-size/
  - WCAG 2.5.5 (AAA): **44×44 CSS px**. https://w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html
  - Material **48×48** (https://ishadeed.com/article/target-size/). Microsoft **7.5 mm**, and "targets that have severe consequences if touched in error should have greater padding and be placed further from the edge". https://learn.microsoft.com/en-us/windows/uwp/design/input/guidelines-for-targeting
  - Chen et al. 2012 (bare finger), buttons of 10-30 mm: misses fell 84% from 10 to 30 mm. **Low-error-tolerance tasks: at least 30 mm.** It also reports other standards: ANSI/HFES 100 at least 9.5 mm; Monterey 19 mm with a 6 mm gap; ISO 9241-9 about 22 mm. https://pmc.ncbi.nlm.nih.gov/articles/PMC3572909
  - Gloved figures (thin glove at least 20 mm, thick 25 mm) come only from a vendor and are uncited. https://www.cdtech-display.com/knowledges/how-to-optimize-ui-button-size-for-gloved-users-in-industrial-hmis/ (**unverified**). Whether capacitive phones register glove touches depends on the glove material (https://fieldscale.com/blog/touch-screens-with-gloves-on/). Test with the plant's own gloves.
  - My estimate: 390 CSS px over ~64 mm of glass gives **1 CSS px ≈ 0.16 mm** (10 mm ≈ 60 px). Check on the target phone.
- **One hand**: 49% one-handed, 36% cradled, 15% two-handed. Keep dangerous controls out of the top-left. Hoober later said people hit the **centre** most accurately. https://uxmatters.com/mt/archives/2013/02/how-do-users-really-hold-mobile-devices.php
- **Glare**: reflected ambient light washes out darks and small luminance steps; ~20,000 lux leaves images "barely visible". https://displaymate.com/Smartphone_Brightness_ShootOut_1.htm . Light mode wins most of the time; in daylight polarity made no difference. https://www.nngroup.com/articles/dark-mode/ → light theme, 7:1 body text (https://www.w3.org/WAI/WCAG21/Understanding/contrast-enhanced), no pale-grey text, no meaning in pale tints.

---

## 8. Recommended patterns for OUR screens

Source tags: [MX] MaintainX, [UK] UpKeep, [FX] Fiix, [LM] Limble, [SAP], [MAX] Maximo, [DZ] Dozuki/iFixit, [TU] Tulip, [AUG] Augmentir, [ISA] ISA-101/HP-HMI, [ASM], [NE107], [ISO] 3864/7010, [Z535], [OSHA] 1910.145/.147, [PAL] Palmer, [AND] Andon/Vorne, [SF] Salesforce FS, [TH] Thai typography sources, [TGT] target-size sources, [GLR] glare sources, [HOO] Hoober.

### 8.1 Technician job (phone)
1. Open on **the one current job**: large Thai machine name, code small [ASM]; one line why, one line when (clock time + live relative), location; the queue collapsed to "next: N jobs" [MAX].
2. **Accept / Start = one full-width bottom button.** "Disagree with priority" is a secondary button opening a reason list, like Reject [MAX]. After start, a running timer in the header [MX][MAX][DZ].
3. Status words limited to: waiting, in progress, paused (with reason), done [MX][UK].
4. **Offline state always visible**: "saved on this phone, not sent yet (n)" until acknowledged [UK gap]. Never drop input [DZ gap].
5. Print is secondary and mirrors the screen's structure [DZ PDF].

### 8.2 Step-by-step procedure (phone)
1. **One step per screen**, fixed order: "3/6", Thai instruction (18-20 px looped), English manual line smaller, "manual p.144" button, evidence field, sticky full-width **Done → next** [DZ][TU][HOO]. The full list lives in an "all steps" sheet.
2. Bullets: instruction / note / reminder / **caution, rarely** [DZ]. Hazards: Thai Z535 signal word + ISO-geometry pictogram; colours only in their standard meaning [Z535][ISO].
3. **Typed evidence** where the playbook defines it: pass/flag/fail (flag/fail asks what was found), number with unit and range, photo. Required fields block Next and say what is missing [MX][DZ].
4. **Isolation step** (only when the backend marks it) [OSHA][SAP]:
   header "ตัดพลังงาน / ล็อกเอาต์" + energy type/magnitude from the manual; one row per isolating device (location, *not locked → locked*, "my lock no.", optional photo); then a separate **"verified zero energy (try-start)"** confirmation that cannot be pre-ticked. The only deliberate friction in the app: hold or two-tap confirm [TU]. Release mirrors OSHA (e): area clear, people clear, notify, remove only your own lock.
5. A wait step (for example "cool 30 min") shows a countdown and a **W017** hot-surface mark [ISO][DZ target time].
6. The manual page opens in place, with a sticky "back to step 3" [owner-trial run 3].
7. Pause / hand over is reachable from every step. The handover requires a note [DZ pause/handoff].

### 8.3 Close job (phone)
1. **Outcome = 4 large segmented choices** (fixed / temporary / not fixed / no fault found), not a dropdown [FX].
2. **Time prefilled from the timer**, editable; "waited n min" by stepper + reason (parts / line stop / help / other) [MX].
3. Unreached steps: "steps 3-6 not done" with **Go back** / **Close anyway** [FX].
4. Failure codes optional; if adopted, problem → cause → action [FX][MAX].
5. Confirmation names machine and outcome, offers the next job [owner-trial].

### 8.4 Operator fault report (phone)
1. **QR on the machine opens the form prefilled** [LM]; otherwise station → machine picker, never a typed code.
2. Three inputs: urgency (2-3 large choices in consequences: "line stopped" / "still running"), what was seen (chips + text), optional photo.
3. Duplicate guard names the open job in words; **"เรื่องที่คุณแจ้งไว้"** below with live status [owner-trial].

### 8.5 Shift-lead board (desk / tablet)
1. **10-second scan, top-down**: (a) any line stopped (red, Andon) [AND]; (b) proposals waiting for me (count, oldest wait); (c) at risk: ETA before shift end or no qualified technician (triangle + text) [SF]; (d) load band with committed vs capacity minutes [MX].
2. **Decision queue = one table sorted by priority score**: priority (shape+label+colour) | machine (Thai) + symptom | lost units if it waits | ETA ± band | skill | proposed technician | Confirm (filled) · Other technician · Set aside (reason). "Why" is one line, full reason on expand [PAL][SF].
3. **Swimlanes**: row per rostered technician over the shift, blocks for confirmed/in-progress jobs, skill tags; read-only, no drag; the optimiser proposes [MX][SF].
4. Held back / set aside this shift / done this shift = collapsible sections under the table.
5. Every action: a one-line banner naming machine and person; the board self-refreshes and shows "updated hh:mm" [owner-trial].

### 8.6 Line overview (desk / wall)
1. **ISA L1, no actions**: horizontal station sequence, buffers in units between, bottleneck marked by shape + word [ISA][ASM].
2. **Grey when normal; colour only on abnormal stations** (Andon meanings; no green for running) [ISA][AND].
3. Abnormal machines get an **embedded mini-trend with threshold band and projected ETA band** [ISA][ASM]; sensor health in NE107 words, apart from job priority [NE107].
4. Click → L2/L3 machine detail; health ranking lives at L3 [ISA].

### 8.7 Engineer review (desk)
1. **Line-by-line split**: manual text left, draft (EN + TH) right, approve/edit per line, figure check inline [DZ].
2. Gaps, "manual has no answer" and loops: **separate lists with counts** [owner-trial].
3. Per step: typed evidence field and an "isolation step" flag. This is where the technician's safety data is created [MX][SAP][OSHA].
4. Required skill chosen by Thai name [AUG][PAL].

### 8.8 Visual system (all screens)
- Neutral grey/ink chrome. **One interactive colour** (a dark ink-blue) that never overlaps status hues. A status hue appears only when something is abnormal [ISA][TU].
- **Line-icon set drawn by us** (SVG), always paired with text. No emoji [owner verdict][MAX avoid].
- Tables and aligned columns instead of cards with coloured borders. Machine IDs in mono at secondary weight [ASM].

---

## 9. Checkable design rules

**Type (Thai)**
1. Body/reading Thai uses a **looped** face (Plex Sans Thai Looped or Noto Sans Thai Looped). Loopless only ≥ 24 px headings. [TH]
2. Phone body text ≥ 17 px; nothing below 14 px anywhere; desk body ≥ 15 px. Measured Bo Baimai height ≥ 1.2 mm on the target phone. [TH, TU 13 pt floor]
3. `line-height` ≥ 1.6 for Thai paragraphs, ≥ 1.35 for single-line labels and buttons. No fixed-height text containers. The stack test string must show no clipped marks at any size. [TH]
4. No `text-align: justify`, no `letter-spacing`, no italic and no synthetic oblique on Thai. Bold only on ≤ 1 phrase per block. [TH]
5. All fonts are self-hosted; zero requests to external hosts (check the network panel on an offline LAN). [brief]

**Colour and status**
6. Body text contrast ≥ 7:1 and secondary text ≥ 4.5:1, both on the actual background. [GLR, WCAG]
7. Red is reserved for "line or machine stopped / urgent priority" and DANGER callouts. Amber is reserved for "will breach / high priority" and WARNING. ISO safety yellow+black is used only inside CAUTION/hazard callouts. A hue used for status never appears on a non-status element. [ISA, ISO, Z535]
8. Normal and running states are **not** coloured (no green "ปกติ" pills). Green appears only as a small "done/verified" mark. [ISA]
9. Every priority or status shows at least **two of: shape, text, colour**. In a greyscale screenshot every priority level must still be distinguishable. [ISA]
10. Priority has 4 levels with fixed Thai labels and fixed shapes, and is identical on every screen. [PAL, ISA]
11. No emoji anywhere. Every icon has a visible text label. [owner verdict]

**Touch and layout (phone)**
12. Every tap target ≥ 48×48 CSS px, with ≥ 8 px between adjacent targets. [TGT]
13. The primary action is full width, ≥ 64 px tall, sticky in the bottom zone, and there is **exactly one** filled primary button per screen. [TU, HOO, TGT]
14. Consequential actions (close job, confirm isolation, set aside) sit ≥ 24 px from the primary action and from the screen edge, and need a confirm or hold. Plain step completion needs no confirmation. [MS targeting, TU friction]
15. The current step's instruction plus its primary action fit in the first viewport at 390×844, with no scrolling. [DZ]
16. The fixed bottom nav never overlaps content: the content has bottom padding of at least the nav height. [screenshot defect]
17. Nothing essential in the top-left except Back. [HOO]

**Time and state**
18. Every time is shown as the plant-clock absolute time. Any relative time ("in 40 min") is recomputed at render and shown with the absolute time. ETAs always show the ± range. [owner-trial run 3]
19. Every action gets a result message that names the machine/job and the person, within 1 s. [owner-trial]
20. Unsent offline actions are counted and shown on every screen until acknowledged. [UK gap]

**Safety**
21. An isolation step shows energy type, one row per isolating device with a lock-number field, and a separate zero-energy verification that cannot be pre-checked or batch-checked, in OSHA order. It is shown only when backend data marks the step. [OSHA, SAP]
22. Hazard callouts use the Thai signal word (อันตราย / คำเตือน / ข้อควรระวัง) plus the pictogram. NOTICE-type content (equipment only) never uses the warning triangle. The Thai equivalents are conventional; confirm them against the plant's signs. [Z535, OSHA 1910.145]
23. ≤ 1 caution callout per step. If there are more, split the step. [DZ, TU]

**Board and overview**
24. The shift-lead board answers "line stopped? / waiting for me / at risk / load" above the fold at 1280×800. [AND, SF]
25. The decision queue is one table sorted by priority score; no status kanban columns. [SF, PAL]
26. The overview has no action buttons, and its normal state is grey. [ISA]
27. A machine's Thai name is more prominent than its code everywhere. [ASM]

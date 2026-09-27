"""The text of the evaluation manuals, page by page.

A second synthetic corpus, separate from `fixtures/corpus` (ADR-033), written
to measure retrieval and drafting on material the pipeline was not tuned on.
The first corpus has five symptoms and every change to the drafter since August
was made while looking at them; a figure measured there cannot say how the
pipeline does on a manual it has not seen.

Equipment from a vehicle body shop rather than only robot arms, and the shapes
real maintenance manuals have and the first corpus lacks:

  * **sister models** (SW-210 and SW-310) with the same procedures and
    different figures, so a draft from the wrong model reads perfectly well;
  * a **specification table** that repeats every figure of the procedures, so
    the page with the most matching numbers is not the page with the steps;
  * a **troubleshooting table** that names the symptom in the question's own
    words and points elsewhere for the procedure;
  * a **procedure that runs over two pages**;
  * symptoms the manuals discuss and prescribe nothing for, and symptoms they
    never mention.

Every value is invented. None of it came from a real manual, and none of it
should ever be read as maintenance instruction.
"""

from __future__ import annotations

from fixtures.corpus.pages import Manual, Page

_ABOUT = (
    "This document is a synthetic manual written for testing a retrieval system. "
    "It describes equipment that does not exist. Every procedure, figure and part "
    "number in it is invented and must never be used on equipment."
)

# ── SW-210 servo spot-welding gun ───────────────────────────────────────────

SW210 = Manual(
    filename="sw-210-servo-gun.pdf",
    title="SW-210 Servo Spot Welding Gun - Maintenance",
    machine_model="SW-210",
    edition="Rev B, synthetic",
    pages=(
        Page(1, "About this manual", _ABOUT),
        Page(
            2,
            "Safety and lockout",
            "Before any work on the gun, make the cell safe.\n\n"
            "1. Stop the robot program and switch the cell to manual mode.\n"
            "2. Switch off the weld controller and lock breaker WB-2 with a personal lock.\n"
            "3. Close the cooling water supply valve CW-1 and vent the line.\n"
            "4. Wait 3 minutes for the servo amplifier to discharge before opening any cover.\n\n"
            "Electrode caps are hot for several minutes after the last weld.",
        ),
        Page(
            3,
            "Gun overview",
            "The SW-210 is a C-type servo gun. A servo motor drives the moving electrode "
            "through a ball screw; the fixed arm carries the lower electrode. Both "
            "electrodes are water cooled through the shanks.\n\n"
            "Poor weld quality usually traces to one of three things: worn electrode "
            "tips, low cooling water flow, or incorrect gun force. Weld expulsion and "
            "small nuggets are symptoms, not causes; check the tips first.",
        ),
        Page(
            4,
            "Electrode tip wear - corrective procedure",
            "Symptom: tip face diameter above 7.5 mm, or nugget size below specification "
            "on the teardown coupon.\n\n"
            "1. Make the cell safe following the lockout on page 2.\n"
            "2. Measure the tip face diameter with the tip gauge. Above 7.5 mm the caps "
            "must be dressed or replaced.\n"
            "3. If the caps have more than 1.5 mm of material left, run the tip dresser "
            "cycle and re-measure.\n"
            "4. Otherwise pull both caps with the cap remover and fit new caps by hand.\n"
            "5. Check tip-to-tip alignment with carbon paper. Misalignment must be within "
            "0.5 mm.\n"
            "6. Weld one coupon and check the nugget is at least 5 mm.\n"
            "Required tools: tip gauge, cap remover, carbon paper.\n"
            "Estimated time: 20 minutes. Required skill: robot mechanical.",
        ),
        Page(
            5,
            "Cooling water flow low - corrective procedure",
            "Symptom: cooling water flow below 4 L/min at the return flow switch.\n\n"
            "1. Make the cell safe following the lockout on page 2.\n"
            "2. Check the supply pressure gauge reads at least 3 bar.\n"
            "3. Remove and clean the inline strainer. Replace the element if torn.\n"
            "4. Inspect both shank hoses for kinks at the gun rotation point.\n"
            "5. Reopen CW-1 and confirm return flow reaches 6 L/min within 30 seconds.\n"
            "Required tools: strainer wrench, flashlight.\n"
            "Estimated time: 30 minutes. Required skill: robot mechanical.",
        ),
        Page(
            6,
            "Gun servo motor overheating - corrective procedure",
            "Symptom: gun motor temperature above 90 degrees Celsius.\n\n"
            "1. Make the cell safe following the lockout on page 2.\n"
            "2. Remove the motor cover. Its four bolts are torqued to 8 Nm.\n"
            "3. Clean the motor fins and check the cooling fan turns freely.\n"
            "4. Grease the ball screw with 15 g of the specified grease.\n"
            "5. Refit the cover and run 50 test strokes; the motor must stay below "
            "70 degrees Celsius.\n"
            "Required tools: torque wrench 5-60 Nm, grease gun.\n"
            "Estimated time: 45 minutes. Required skill: robot mechanical.",
        ),
        Page(
            7,
            "Specifications",
            "Gun force: 3.5 kN. Tip face diameter limit: 7.5 mm. Tip alignment limit: "
            "0.5 mm. Minimum nugget: 5 mm.\n\n"
            "Cooling water: nominal 6 L/min, alarm below 4 L/min, supply at least 3 bar.\n\n"
            "Motor cover bolts: 8 Nm. Ball screw grease: 15 g every 250,000 welds. "
            "Motor temperature alarm: 90 degrees Celsius.\n\n"
            "Secondary cable life: 1,000,000 cycles. Cable clamp bolts: 20 Nm.",
        ),
        Page(
            8,
            "Troubleshooting",
            "Weld expulsion or splash: worn or misaligned tips, see page 4.\n\n"
            "Cooling water alarm: see page 5.\n\n"
            "Gun motor temperature alarm: see page 6.\n\n"
            "Gun does not close fully or stops short of the programmed stroke: the "
            "cause depends on which servo amplifier alarm is shown. There is no field "
            "procedure for this fault. Read the alarm code, do not force the gun "
            "closed by hand, and contact the gun service engineer.",
        ),
        Page(
            9,
            "Secondary cable replacement",
            "Symptom: cable jacket cracked, or cable at end of life at 1,000,000 cycles.\n\n"
            "1. Make the cell safe following the lockout on page 2.\n"
            "2. Close CW-1 and drain the cable cooling circuit into a tray.\n"
            "3. Remove the two cable clamp bolts at the transformer end.\n"
            "4. Remove the two cable clamp bolts at the gun end and lift the cable out. "
            "Continued on page 10.",
        ),
        Page(
            10,
            "Secondary cable replacement (continued)",
            "5. Fit the new cable with the twist marker facing up.\n"
            "6. Torque all four cable clamp bolts to 20 Nm.\n"
            "7. Reopen CW-1, check for leaks, and weld one test coupon.\n"
            "Required tools: torque wrench 5-60 Nm, drain tray.\n"
            "Estimated time: 60 minutes. Required skill: electrical.",
        ),
    ),
)

# ── SW-310, the sister model: same procedures, different figures ────────────

SW310 = Manual(
    filename="sw-310-servo-gun.pdf",
    title="SW-310 Servo Spot Welding Gun - Maintenance",
    machine_model="SW-310",
    edition="Rev A, synthetic",
    pages=(
        Page(1, "About this manual", _ABOUT),
        Page(
            2,
            "Safety and lockout",
            "Before any work on the gun, make the cell safe.\n\n"
            "1. Stop the robot program and switch the cell to manual mode.\n"
            "2. Switch off the weld controller and lock breaker WB-4 with a personal lock.\n"
            "3. Close the cooling water supply valve CW-3 and vent the line.\n"
            "4. Wait 5 minutes for the servo amplifier to discharge before opening any cover.",
        ),
        Page(
            3,
            "Electrode tip wear - corrective procedure",
            "Symptom: tip face diameter above 8 mm, or nugget size below specification.\n\n"
            "1. Make the cell safe following the lockout on page 2.\n"
            "2. Measure the tip face diameter with the tip gauge. Above 8 mm the caps "
            "must be dressed or replaced.\n"
            "3. If the caps have more than 2 mm of material left, run the tip dresser "
            "cycle and re-measure.\n"
            "4. Otherwise pull both caps with the cap remover and fit new caps by hand.\n"
            "5. Check tip-to-tip alignment with carbon paper. Misalignment must be within "
            "0.8 mm.\n"
            "6. Weld one coupon and check the nugget is at least 6 mm.\n"
            "Required tools: tip gauge, cap remover, carbon paper.\n"
            "Estimated time: 25 minutes. Required skill: robot mechanical.",
        ),
        Page(
            4,
            "Cooling water flow low - corrective procedure",
            "Symptom: cooling water flow below 5 L/min at the return flow switch.\n\n"
            "1. Make the cell safe following the lockout on page 2.\n"
            "2. Check the supply pressure gauge reads at least 4 bar.\n"
            "3. Remove and clean the inline strainer. Replace the element if torn.\n"
            "4. Inspect both shank hoses for kinks at the gun rotation point.\n"
            "5. Reopen CW-3 and confirm return flow reaches 8 L/min within 45 seconds.\n"
            "Required tools: strainer wrench, flashlight.\n"
            "Estimated time: 30 minutes. Required skill: robot mechanical.",
        ),
        Page(
            5,
            "Gun servo motor overheating - corrective procedure",
            "Symptom: gun motor temperature above 95 degrees Celsius.\n\n"
            "1. Make the cell safe following the lockout on page 2.\n"
            "2. Remove the motor cover. Its six bolts are torqued to 10 Nm.\n"
            "3. Clean the motor fins and check the cooling fan turns freely.\n"
            "4. Grease the ball screw with 20 g of the specified grease.\n"
            "5. Refit the cover and run 50 test strokes; the motor must stay below "
            "75 degrees Celsius.\n"
            "Required tools: torque wrench 5-60 Nm, grease gun.\n"
            "Estimated time: 50 minutes. Required skill: robot mechanical.",
        ),
        Page(
            6,
            "Specifications",
            "Gun force: 5 kN. Tip face diameter limit: 8 mm. Tip alignment limit: 0.8 mm. "
            "Minimum nugget: 6 mm.\n\n"
            "Cooling water: nominal 8 L/min, alarm below 5 L/min, supply at least 4 bar.\n\n"
            "Motor cover bolts: 10 Nm. Ball screw grease: 20 g every 200,000 welds. "
            "Motor temperature alarm: 95 degrees Celsius.",
        ),
    ),
)

# ── CV-500 skid conveyor ────────────────────────────────────────────────────

CV500 = Manual(
    filename="cv-500-skid-conveyor.pdf",
    title="CV-500 Skid Conveyor - Maintenance",
    machine_model="CV-500",
    edition="Edition 2, synthetic",
    pages=(
        Page(1, "About this manual", _ABOUT),
        Page(
            2,
            "Safety and lockout",
            "Before any work on the conveyor, stop and isolate the zone.\n\n"
            "1. Stop the zone from the zone control panel and wait for all skids to halt.\n"
            "2. Open isolator Q1 and apply a personal lock and tag.\n"
            "3. Lower the lift table to its mechanical stops and close hydraulic valve HV-1.\n"
            "4. Verify zero energy by pressing the zone start button; nothing may move.",
        ),
        Page(
            3,
            "Conveyor overview",
            "Each zone has a drive station with a geared motor and a roller chain, "
            "carrier rollers that support the skid, a hydraulic lift table at the "
            "transfer point, and a retro-reflective photo-eye that detects skid "
            "presence.\n\n"
            "Most stoppages are overload trips at the drive or a missed skid at the "
            "photo-eye. Noise from the carrier rollers is common and is usually not "
            "urgent.",
        ),
        Page(
            4,
            "Drive chain elongation - corrective procedure",
            "Symptom: chain elongation above 2 percent measured over 10 links.\n\n"
            "1. Stop and isolate the zone following page 2.\n"
            "2. Measure the length of 10 links with the chain gauge.\n"
            "3. Up to 3 percent, slacken the tensioner bolts, move the take-up until "
            "the chain sags 15 mm at mid-span, and retighten the tensioner bolts to 45 Nm.\n"
            "4. Above 3 percent, replace the chain; tensioning cannot recover it.\n"
            "5. Run the zone empty for 10 minutes and listen for chain slap.\n"
            "Required tools: chain gauge, torque wrench 20-100 Nm.\n"
            "Estimated time: 40 minutes. Required skill: robot mechanical.",
        ),
        Page(
            5,
            "Drive motor overload trip - corrective procedure",
            "Symptom: drive motor current above 18 A, or the overload relay trips.\n\n"
            "1. Stop and isolate the zone following page 2.\n"
            "2. Walk the zone and remove anything jamming a skid or roller.\n"
            "3. Check the gearbox oil level at the sight glass. Top up to the mark; the "
            "gearbox holds 2.5 L.\n"
            "4. Check the overload relay is set to 16 A and reset it.\n"
            "5. Restart the zone and confirm running current is below 12 A.\n"
            "Required tools: gearbox oil, multimeter with clamp.\n"
            "Estimated time: 35 minutes. Required skill: electrical.",
        ),
        Page(
            6,
            "Lift table hydraulic pressure low - corrective procedure",
            "Symptom: lift table system pressure below 90 bar.\n\n"
            "1. Stop and isolate the zone following page 2.\n"
            "2. Check the tank oil level; top up with the specified oil to the upper mark.\n"
            "3. Replace the return filter element if its indicator is red.\n"
            "4. Check the relief valve setting and adjust it to 110 bar.\n"
            "5. Cycle the lift table 5 times and confirm pressure holds above 100 bar.\n"
            "Required tools: pressure gauge 0-250 bar, filter wrench.\n"
            "Estimated time: 45 minutes. Required skill: hydraulics.",
        ),
        Page(
            7,
            "Carrier rollers",
            "Carrier rollers are sealed for life. Noise from a roller can be bearing "
            "wear, debris on the tread, or a skid runner that is out of true, and "
            "which of these it is cannot be told from the noise alone. The rollers "
            "are replaced as complete assemblies by the conveyor service team; there "
            "is no field repair. Mark the noisy roller and report it.",
        ),
        Page(
            8,
            "Skid presence photo-eye - corrective procedure",
            "Symptom: skid not detected, or the photo-eye signal flickers as a skid passes.\n\n"
            "1. Stop the zone. Isolation is not required for this task.\n"
            "2. Clean the sensor lens and the reflector with a dry cloth.\n"
            "3. Align the sensor so the beam hits the reflector centre; the alignment "
            "LED must be steady green.\n"
            "4. Check the reflector bracket screws are tight.\n"
            "5. Pass an empty skid and confirm one clean signal.\n"
            "Required tools: lint-free cloth, 4 mm hex key.\n"
            "Estimated time: 15 minutes. Required skill: electrical.",
        ),
        Page(
            9,
            "Troubleshooting",
            "Overload trip at the drive: see page 5.\n\n"
            "Chain slap or chain jumping the sprocket: see page 4.\n\n"
            "Lift table slow or not reaching the top: see page 6.\n\n"
            "Skid stops short of the transfer point: check the photo-eye, see page 8.\n\n"
            "Roller noise: see page 7.",
        ),
    ),
)

# ── SD-30 sealer dispensing unit ────────────────────────────────────────────

SD30 = Manual(
    filename="sd-30-sealer-dispenser.pdf",
    title="SD-30 Sealer Dispensing Unit - Maintenance",
    machine_model="SD-30",
    edition="Edition 1, synthetic",
    pages=(
        Page(1, "About this manual", _ABOUT),
        Page(
            2,
            "Safety and depressurising",
            "The material system works at up to 200 bar. A nozzle opened under "
            "pressure injects sealer through the skin.\n\n"
            "1. Stop the pump and close the material supply valve MV-1.\n"
            "2. Open the dump valve DV-1 into a waste container until the gauge reads 0 bar.\n"
            "3. Switch off the hose heaters and let them cool for 10 minutes.\n"
            "4. Lock the pump air supply valve with a personal lock.",
        ),
        Page(
            3,
            "Dispensing overview",
            "The pump draws sealer from a drum and pushes it through heated hoses to "
            "the dispensing gun on the robot. Bead width depends on material "
            "pressure, material temperature, nozzle condition and robot speed.\n\n"
            "An irregular or broken bead pattern has so many possible causes that "
            "no single procedure applies; record the bead with a photo and the "
            "pressure and temperature readings, and ask the process engineer.",
        ),
        Page(
            4,
            "Nozzle clogging - corrective procedure",
            "Symptom: bead width below 3 mm, or the bead thins along the seam.\n\n"
            "1. Depressurise the system following page 2.\n"
            "2. Unscrew the nozzle and inspect the orifice against light.\n"
            "3. Soak the nozzle in the approved cleaner for 20 minutes, then blow it "
            "through with air.\n"
            "4. Replace the nozzle if the orifice is damaged.\n"
            "5. Refit the nozzle and torque it to 12 Nm.\n"
            "6. Dispense a test bead and confirm the width is 4 to 5 mm.\n"
            "Required tools: nozzle wrench, torque wrench 5-60 Nm, cleaning pot.\n"
            "Estimated time: 35 minutes. Required skill: robot mechanical.",
        ),
        Page(
            5,
            "Material supply pressure low - corrective procedure",
            "Symptom: supply pressure below 150 bar at the pump outlet.\n\n"
            "1. Depressurise the system following page 2.\n"
            "2. Check the drum is not empty and the follower plate is seated.\n"
            "3. Replace the pump outlet filter element; it is 60 mesh.\n"
            "4. Inspect the pump throat seal for material leaks and replace it if leaking.\n"
            "5. Restart the pump and confirm outlet pressure reaches 180 bar.\n"
            "Required tools: filter wrench, seal kit, waste container.\n"
            "Estimated time: 50 minutes. Required skill: hydraulics.",
        ),
        Page(
            6,
            "Hose heater fault - corrective procedure",
            "Symptom: hose temperature below 40 degrees Celsius with the set point at "
            "45 degrees Celsius.\n\n"
            "1. Switch off the hose heater circuit at the heater panel and lock it.\n"
            "2. Check fuse F3 in the heater panel; it is a 10 A fuse.\n"
            "3. Measure the thermocouple at terminals T7 and T8; an open circuit "
            "means the thermocouple is broken.\n"
            "4. Measure the heater element resistance; it should read 40 to 50 ohm.\n"
            "5. Restore power and confirm the hose reaches 45 degrees Celsius within "
            "15 minutes.\n"
            "Required tools: multimeter, spare fuse.\n"
            "Estimated time: 30 minutes. Required skill: electrical.",
        ),
        Page(
            7,
            "Specifications",
            "Maximum material pressure: 200 bar. Normal supply pressure: 180 bar, "
            "alarm below 150 bar.\n\n"
            "Hose set point: 45 degrees Celsius, alarm below 40. Heater fuse F3: 10 A. "
            "Heater element: 40 to 50 ohm.\n\n"
            "Nozzle torque: 12 Nm. Bead width: 4 to 5 mm, alarm below 3 mm. Outlet "
            "filter: 60 mesh.",
        ),
    ),
)

MANUALS = (SW210, SW310, CV500, SD30)

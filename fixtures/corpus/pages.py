"""The text of the two synthetic manuals, page by page (ADR-033).

Kept as data rather than embedded in the generator, because this is the part
that gets read and argued with. The generator only lays it out.

Written to contain the mistakes worth catching, not to look like a manual:

  * the same symptom documented for both machine models, with **different
    torque figures** - the case per-step provenance exists to detect, and the
    one ADR-015 says reviewers are worst at (a step from the wrong model reads
    perfectly well)
  * a figure on the correct page that belongs to a different fastener, so the
    authoring gate has a number it must refuse to accept as evidence
  * a page describing the right component for the wrong reason, so a retriever
    matching on component alone scores it too highly
  * one symptom `rules.yaml` can raise with nothing written about it anywhere,
    so the "not found" path is reachable

Every value here is invented. None of it came from a real manual, and none of
it should ever be read as maintenance instruction.
"""

from __future__ import annotations

from typing import NamedTuple


class Page(NamedTuple):
    number: int
    heading: str
    body: str


class Manual(NamedTuple):
    filename: str
    title: str
    machine_model: str
    edition: str
    pages: tuple[Page, ...]


# ── R-2000iC ────────────────────────────────────────────────────────────────

R2000IC = Manual(
    filename="r-2000ic-maintenance.pdf",
    title="R-2000iC Maintenance Manual",
    machine_model="R-2000iC",
    edition="Edition 3, synthetic",
    pages=(
        Page(
            1,
            "About this manual",
            "This document is a synthetic manual written for testing. It describes a "
            "machine that does not exist. Every procedure, figure and part number in "
            "it is invented and must never be used on equipment.\n\n"
            "Sections are ordered by subsystem: drive and belt, servo axes, cooling, "
            "hydraulics, and safety interlocks.",
        ),
        Page(
            2,
            "Safety and lockout",
            "Before any maintenance task in this manual, isolate the cell.\n\n"
            "1. Press the emergency stop on the cell control panel.\n"
            "2. Open breaker CP-3 at the cell distribution box and apply a personal "
            "lock and tag.\n"
            "3. Wait 5 minutes for the DC bus to discharge before removing any cover.\n"
            "4. Verify zero energy at test points TP-1 and TP-2 before proceeding.\n\n"
            "The 5 minute wait is a minimum. Do not shorten it on the basis of a "
            "meter reading alone.",
        ),
        Page(
            3,
            "Drive belt and belt motor",
            "The belt motor drives the main axis through a toothed belt. Normal "
            "running temperature is 55 to 70 degrees Celsius measured at the motor "
            "housing sensor.\n\n"
            "A motor running above 85 degrees Celsius indicates belt tension outside "
            "specification, a failing bearing, or restricted airflow at the motor fan "
            "shroud. Investigate in that order: tension is the most common cause and "
            "the fastest to check.",
        ),
        Page(
            4,
            "Belt motor overheating - corrective procedure",
            "Symptom: belt motor temperature above 85 degrees Celsius.\n\n"
            "1. Isolate the cell following the lockout procedure on page 2.\n"
            "2. Remove the belt guard. The guard is held by four M6 bolts torqued to "
            "10 Nm.\n"
            "3. Measure belt deflection at the midpoint of the longest span. "
            "Deflection must be 4 to 6 mm under 20 N of applied force.\n"
            "4. If deflection is outside that range, slacken the motor mount bolts "
            "and reset tension. Retighten the motor mount bolts to 42 Nm.\n"
            "5. Inspect the fan shroud for accumulated debris and clear it.\n"
            "6. Refit the guard, remove locks, and run the axis for 20 minutes. "
            "Confirm the housing temperature settles below 70 degrees Celsius.\n\n"
            "Required tools: torque wrench 5-60 Nm, belt tension gauge, 10 mm socket.\n"
            "Estimated time: 45 minutes. Required skill: robot mechanical.",
        ),
        Page(
            5,
            "Belt replacement",
            "Replace the toothed belt at 8000 operating hours, or earlier if "
            "cracking is visible at the tooth root.\n\n"
            "The procedure is the same as the tensioning procedure on page 4 up to "
            "step 3, then the belt is removed over the idler. The motor mount bolts "
            "are torqued to 42 Nm on reassembly. The idler bolt is torqued to 18 Nm; "
            "this figure applies to the idler only and not to the motor mount.",
        ),
        Page(
            6,
            "Servo axes - overview",
            "Axes 1 through 6 are driven by brushless servo motors with absolute "
            "encoders. Nominal continuous current per axis is 8 A. Axis 1 carries "
            "the greatest load and runs closest to its limit in normal operation.",
        ),
        Page(
            7,
            "Servo axis 1 - current above specification",
            "Symptom: axis 1 continuous current above 12.5 A.\n\n"
            "Rising current on axis 1 without a change in payload indicates "
            "increasing mechanical resistance: gearbox wear, insufficient grease, or "
            "a partially seized bearing.\n\n"
            "1. Isolate the cell following the lockout procedure on page 2.\n"
            "2. With the brake released, check axis 1 for free movement by hand "
            "through its full travel.\n"
            "3. Remove the gearbox inspection plug and check grease condition. "
            "Metallic content indicates gear wear and the gearbox must be scheduled "
            "for replacement rather than regreased.\n"
            "4. If grease is clean, regrease with 90 g of the specified compound.\n"
            "5. Refit the inspection plug and torque it to 12 Nm.\n"
            "6. Run the axis unloaded for 10 minutes and confirm current returns "
            "below 9 A.\n\n"
            "Required tools: grease gun, torque wrench 5-60 Nm, inspection mirror.\n"
            "Estimated time: 60 minutes. Required skill: robot mechanical.",
        ),
        Page(
            8,
            "Servo axis 2 - current above specification",
            "Symptom: axis 2 continuous current above 11 A.\n\n"
            "The procedure is identical to axis 1 on page 7 except that axis 2 takes "
            "60 g of grease and its inspection plug is torqued to 8 Nm. Axis 2 is "
            "smaller and its limits are lower; do not apply axis 1 figures to it.",
        ),
        Page(
            9,
            "Cooling fan",
            "The controller cabinet fan runs continuously while the drive is "
            "enabled. Nominal speed is 1500 rpm. A fan below 1200 rpm no longer "
            "moves enough air to hold the cabinet within its rated temperature and "
            "must be replaced rather than cleaned.\n\n"
            "Fan replacement on this model requires the cabinet to be de-energised "
            "and is covered by the general electrical procedure, not by a dedicated "
            "section.",
        ),
        Page(
            10,
            "Hydraulic pump",
            "The clamp hydraulic pump maintains 140 bar in the accumulator. Pressure "
            "loss over a 30 minute idle period should not exceed 8 bar. Greater loss "
            "indicates a failing check valve or a leaking cylinder seal.",
        ),
        Page(
            11,
            "Safety interlocks",
            "Each cell gate carries a dual-channel interlock switch. The controller "
            "reads both channels and expects them to agree.\n\n"
            "An interlock reported open while the gate is physically closed is a "
            "fault in the switch, the wiring, or the controller input, and the cell "
            "must not be returned to production until the cause has been found. "
            "Bypassing an interlock to continue production is prohibited under all "
            "circumstances.\n\n"
            "Diagnosis of an interlock fault is a controls task, not a mechanical "
            "one, and no step-by-step repair is given here because the correct "
            "action depends on which channel disagrees.",
        ),
    ),
)


# ── M-710iC ─────────────────────────────────────────────────────────────────

M710IC = Manual(
    filename="m-710ic-maintenance.pdf",
    title="M-710iC Maintenance Manual",
    machine_model="M-710iC",
    edition="Edition 1, synthetic",
    pages=(
        Page(
            1,
            "About this manual",
            "This document is a synthetic manual written for testing. It describes a "
            "machine that does not exist. Every procedure, figure and part number in "
            "it is invented and must never be used on equipment.\n\n"
            "The M-710iC is a smaller handling robot. Several procedures resemble "
            "those of the R-2000iC and the figures are not the same.",
        ),
        Page(
            2,
            "Safety and lockout",
            "Before any maintenance task in this manual, isolate the cell.\n\n"
            "1. Press the emergency stop on the cell control panel.\n"
            "2. Open breaker CP-7 at the cell distribution box and apply a personal "
            "lock and tag.\n"
            "3. Wait 3 minutes for the DC bus to discharge before removing any cover.\n"
            "4. Verify zero energy at test point TP-1 before proceeding.\n\n"
            "Note that the breaker designation and the discharge time differ from "
            "the R-2000iC.",
        ),
        Page(
            3,
            "Drive belt and belt motor",
            "The belt motor drives the main axis through a toothed belt. Normal "
            "running temperature is 50 to 65 degrees Celsius at the housing sensor.\n\n"
            "A motor running above 80 degrees Celsius indicates belt tension outside "
            "specification or restricted airflow.",
        ),
        Page(
            4,
            "Belt motor overheating - corrective procedure",
            "Symptom: belt motor temperature above 80 degrees Celsius.\n\n"
            "1. Isolate the cell following the lockout procedure on page 2.\n"
            "2. Remove the belt guard. The guard is held by three M5 bolts torqued "
            "to 6 Nm.\n"
            "3. Measure belt deflection at the midpoint of the longest span. "
            "Deflection must be 3 to 5 mm under 15 N of applied force.\n"
            "4. If deflection is outside that range, slacken the motor mount bolts "
            "and reset tension. Retighten the motor mount bolts to 28 Nm.\n"
            "5. Refit the guard, remove locks, and run the axis for 15 minutes.\n\n"
            "Required tools: torque wrench 5-60 Nm, belt tension gauge, 8 mm socket.\n"
            "Estimated time: 35 minutes. Required skill: robot mechanical.",
        ),
        Page(
            5,
            "Cooling fan - speed below specification",
            "Symptom: cabinet fan below 1200 rpm.\n\n"
            "A fan slowing below 1200 rpm has a worn bearing or an obstructed "
            "impeller. Cleaning restores speed only temporarily once the bearing has "
            "started to fail, so the fan is replaced rather than serviced.\n\n"
            "1. Isolate the cabinet following the lockout procedure on page 2.\n"
            "2. Wait for the cabinet to cool. Surfaces inside remain hot for several "
            "minutes after the drive is disabled.\n"
            "3. Disconnect the fan connector at terminal block X4.\n"
            "4. Remove the four fan mounting screws torqued to 3 Nm and withdraw the "
            "fan assembly.\n"
            "5. Fit the replacement, torque the mounting screws to 3 Nm, and "
            "reconnect X4.\n"
            "6. Restore power and confirm the fan reaches 1500 rpm within 30 seconds.\n\n"
            "Required tools: 3 mm hex driver, torque screwdriver 1-5 Nm.\n"
            "Estimated time: 25 minutes. Required skill: electrical.",
        ),
        Page(
            6,
            "Cabinet filter",
            "The cabinet intake filter is cleaned monthly. A blocked filter raises "
            "cabinet temperature without changing fan speed, so filter condition "
            "cannot be inferred from the fan speed reading and must be inspected "
            "directly.",
        ),
        Page(
            7,
            "Servo axis 1",
            "Axis 1 is driven by a brushless servo motor with an absolute encoder. "
            "Nominal continuous current is 6 A. This model has no published "
            "corrective procedure for high axis current; refer the case to the "
            "supplier.",
        ),
        # There is deliberately no page about cycle time. R-cycle-time-drift can
        # fire on this model, and a robot manual has nothing to say about a
        # figure the line controller measures - so the retriever finds nothing,
        # and the "not found, ask an engineer" path becomes reachable in a test
        # rather than first executing in front of a technician (ADR-033).
    ),
)


MANUALS: tuple[Manual, ...] = (R2000IC, M710IC)

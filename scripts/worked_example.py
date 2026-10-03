"""One job, end to end, through the code that runs in the plant.

Run by hand:

    PYTHONPATH=. uv run python scripts/worked_example.py

Every layer here is the shipped function, called in the order the workers call
it, with the database left out: the synthetic signal for MC-001's belt motor
(layer 1), the extractive drafter on the corpus page the answer key names and a
playbook built from its proposal (layer 2), the work order the work module
issues from the Finding, and one dispatch round with a scheduled job beside it
(layer 3). The output is `docs/results/worked-example.md`, so the report quotes
what the system wrote rather than a description of it.

What is left out is said in the output: the database, the reviewer's Thai
rendering of each step (ADR-095), the shift lead's confirmation and the screen.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

from fixtures.corpus.pages import R2000IC
from pdm.contracts import (
    DocumentId,
    FindingRef,
    MachineId,
    MachineModel,
    PlaybookStatus,
    PMTask,
    PMTaskRef,
    Role,
    SkillId,
    SymptomCode,
    UserId,
)
from pdm.contracts.work import Playbook, PlaybookStep
from pdm.dispatch.domain import Queued
from pdm.dispatch.service import planner
from pdm.llm.domain import DraftRequest, Evidence
from pdm.llm.extractive import ExtractiveDrafter
from pdm.platform.config import load_config
from pdm.signals import LINE_A_TWELVE_HOURS, SyntheticSource
from pdm.sim.scenarios import LINE_A_ONE_SHIFT
from pdm.triggers import trend
from pdm.triggers.domain import Outcome, forecast
from pdm.work.domain import from_finding, from_pm_task

OUT = Path("docs/results/worked-example.md")
MACHINE = MachineId("MC-001")
MANUAL = DocumentId("a" * 64)
ENGINEER = UserId("engineer-1")


def main() -> int:
    config = load_config(Path("config"))
    wording = config.wording()
    model = config.model_of(MACHINE)
    fallback = {str(key): table for key, table in config.policy.fallback_minutes.items()}
    policy = config.policy.triggers.trend
    rules = [rule for rule in config.rules.rules if rule.machine_model == model]

    # Layer 1: the first forecast the trend makes on MC-001.
    windows = trend.Window(timedelta(minutes=policy.window_minutes))
    decision = None
    for signal in SyntheticSource(LINE_A_TWELVE_HOURS, seed=20260813).stream():
        if signal.machine_id != MACHINE:
            continue
        found = forecast(
            signal,
            rules,
            machine_model=model,
            now=signal.timestamp,
            windows=windows,
            horizon=timedelta(hours=policy.max_horizon_hours),
            min_samples=policy.min_samples,
            eta_error=[(band.ahead_below_hours, band.fraction) for band in policy.eta_error],
        )
        decision = next((one for one in found if one.outcome is Outcome.FORECAST), None)
        if decision is not None:
            break
    if decision is None or decision.finding is None:
        print("no forecast on MC-001")
        return 1
    finding = decision.finding
    now = finding.detected_at

    # Layer 2: drafted from the page the answer key names, then approved.
    page = next(one for one in R2000IC.pages if one.number == 4)
    proposal = ExtractiveDrafter().propose(
        DraftRequest(
            symptom_code=finding.symptom_code,
            machine_model=MachineModel(model),
            question="the belt motor temperature is above 85 degrees",
            evidence=(
                Evidence(
                    document_id=MANUAL,
                    page=4,
                    text=f"{page.heading}\n\n{page.body}",
                    title=R2000IC.title,
                    machine_model=MachineModel(model),
                    score=0.9,
                ),
            ),
        )
    )
    playbook = Playbook(
        symptom_code=finding.symptom_code,
        machine_model=MachineModel(model),
        steps=tuple(
            PlaybookStep(text=step.text, source_doc=MANUAL, page=step.cites[1], confidence=0.9)
            for step in proposal.steps
        ),
        tools=proposal.tools,
        estimated_minutes=proposal.estimated_minutes or 45,
        required_skill=SkillId("robot_mechanical"),
        source_doc=MANUAL,
        page=4,
        status=PlaybookStatus.APPROVED,
        approved_by=ENGINEER,
        approved_at=now - timedelta(days=1),
        approver_role=Role.ENGINEER,
    )

    # The work order the work module issues from the Finding.
    order = from_finding(
        finding,
        FindingRef("F-0001"),
        playbook=playbook,
        machine_model=model,
        fallback_minutes=fallback,
        wording=wording,
    )

    # Layer 3: one round, with a PM job for another machine waiting beside it.
    pm_config = next(task for task in config.plant.pm_tasks if task.machine_id != MACHINE)
    pm = from_pm_task(
        PMTask(
            pm_task_ref=PMTaskRef(pm_config.pm_task_ref),
            machine_id=pm_config.machine_id,
            symptom_code=SymptomCode(pm_config.symptom_code),
            interval=timedelta(hours=pm_config.interval_hours),
            due_at=now,
        ),
        playbook=None,
        machine_model=config.model_of(pm_config.machine_id),
        fallback_minutes=fallback,
        wording=wording,
    )
    minutes = int(LINE_A_ONE_SHIFT.duration.total_seconds() // 60)
    # The deployed round's own planner (ADR-128), not a choice made here.
    decided = planner(config)(
        [
            Queued(ref="WO-0001", order=order, created_at=now),
            Queued(ref="WO-0002", order=pm, created_at=now),
        ],
        technicians=list(LINE_A_ONE_SHIFT.technicians),
        assignments=[(person.user, minutes) for person in LINE_A_ONE_SHIFT.technicians],
        config=config,
        now=now,
        shift_id=LINE_A_ONE_SHIFT.shift_id,
        on_date=now.date(),
    )

    lines = [
        "# One job, end to end",
        "",
        "**Generated by `scripts/worked_example.py`. Do not edit by hand.**",
        "",
        "## 1. The signal and the Finding (layer 1)",
        "",
        f"- scenario `{LINE_A_TWELVE_HOURS.name}`, seed 20260813, "
        f"`{MACHINE}` `{finding.symptom_code}`",
        f"- first forecast at {wording.clock(now)}: ETA {wording.clock(finding.eta)}"
        if finding.eta
        else f"- first forecast at {wording.clock(now)}",
        f"- decision: {decision.why}",
        "",
        "## 2. The playbook (layer 2)",
        "",
        f"Drafted from `{R2000IC.title}` page 4 by the extractive drafter, kind "
        f"`{proposal.kind.value}`, approved by `{ENGINEER}`. Each step cites its page.",
        "",
        *(
            f"{index}. {step.text} *(p. {step.page})*"
            for index, step in enumerate(playbook.steps, 1)
        ),
        "",
        f"Tools: {', '.join(playbook.tools) or '-'} · estimate {playbook.estimated_minutes} min",
        "",
        "## 3. The work order",
        "",
        f"- `reason` (why this job exists): {order.reason}",
        f"- severity `{order.severity.value}`, estimate {order.estimated_minutes} min"
        f"{' (fallback)' if order.estimate_is_fallback else ''}, skill `{order.required_skill}`",
        "",
        "## 4. The dispatch round (layer 3)",
        "",
        f"- load {decided.load_ratio:.0%}, band `{decided.band.value}`"
        if decided.load_ratio is not None
        else f"- band `{decided.band.value}`",
        f"- summary: {decided.summary}",
        "",
        *(
            f"- **{one.ref}** -> {', '.join(str(a.user) for a in one.assignees)}: "
            f"`priority_reason` = {one.priority_reason}"
            for one in decided.placed
        ),
        *(f"- **{one.ref}** held: {one.why}" for one in decided.held),
        *(f"- **{one.ref}** unassigned: {one.why}" for one in decided.unassigned),
        "",
        "## Not shown here",
        "",
        "The database, the reviewer's Thai rendering of each step (ADR-095), the "
        "shift lead confirming the proposal (ADR-071) and the technician's screen. "
        "Those are the same order read back through the API; the report shows them "
        "as screenshots.",
        "",
    ]
    OUT.write_text("\n".join(lines))
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

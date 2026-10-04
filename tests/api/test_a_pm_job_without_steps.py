"""Where a scheduled job with no approved steps sends the technician.

Fourth trial, finding 11: the PM ticket said "look here" and named a manual
with no page, because a PM task in `plant.yaml` records an interval and never a
page. Principle 5 forbids guessing one, so the ticket says which part of the
manual to open and that no page is on record.
"""

from __future__ import annotations

import re
from pathlib import Path

from pdm.api.dispatch import pm_page_note
from pdm.contracts import WorkOrderOrigin
from pdm.platform.config import load_config

TITLE = "เปลี่ยนสายพานฟัน (ครบรอบบำรุงรักษา)"


def test_the_note_names_the_schedule_section_and_says_no_page_is_recorded() -> None:
    note = pm_page_note(WorkOrderOrigin.SCHEDULED, has_steps=False, task_title=TITLE)

    assert note is not None
    assert "ตารางบำรุงรักษา" in note
    assert "ยังไม่ได้บันทึกเลขหน้า" in note
    assert f"“{TITLE}”" in note


def test_the_note_never_carries_a_page_number() -> None:
    """A digit in this sentence would be a page nobody recorded."""
    note = pm_page_note(WorkOrderOrigin.SCHEDULED, has_steps=False, task_title=None)

    assert note is not None
    assert not re.search(r"\d", note)


def test_only_a_scheduled_job_without_steps_gets_it() -> None:
    assert pm_page_note(WorkOrderOrigin.SCHEDULED, has_steps=True, task_title=TITLE) is None
    for origin in (WorkOrderOrigin.CONDITION, WorkOrderOrigin.MANUAL):
        assert pm_page_note(origin, has_steps=False, task_title=TITLE) is None


def test_no_pm_task_in_the_plant_file_records_a_page() -> None:
    """The premise of the note. If a task ever carries a page, the ticket
    should cite it instead, and this test is where that change starts."""
    config = load_config(Path("config"))

    assert config.pm_tasks
    for task in config.pm_tasks:
        assert "page" not in type(task).model_fields

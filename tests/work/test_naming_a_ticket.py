"""A ticket named the way the floor names it. No database.

The fourth trial found a shift lead reading "ยืนยัน WO-000011 แล้ว" and an
operator unable to tell two of their own reports apart (findings 5, 8, 19).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pdm.contracts import MachineId, Severity, UserId, WorkOrder, WorkOrderOrigin
from pdm.contracts.wording import Wording
from pdm.work import domain

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MOTOR = MachineId("MC-001")
FALLBACK = {"R-2000iC": {Severity.MEDIUM: 45}}
WORDING = Wording(symptom_titles={"motor-overheat": "มอเตอร์สายพานร้อนเกินกำหนด"})


def _reported(description: str) -> WorkOrder:
    return domain.from_report(
        machine_id=MOTOR,
        severity=Severity.MEDIUM,
        reported_by=UserId("op-1"),
        reporter_name="สมใจ",
        description=description,
        playbook=None,
        machine_model="R-2000iC",
        fallback_minutes=FALLBACK,
        now=NOW,
    )


class TestTheReportersWords:
    def test_come_back_without_who_and_when_around_them(self) -> None:
        order = _reported("น้ำมันไหลใต้ฐาน: ประมาณฝ่ามือ")

        assert domain.reported_words(order) == "น้ำมันไหลใต้ฐาน: ประมาณฝ่ามือ"

    def test_an_older_reason_loses_the_tickets_it_named_then(self) -> None:
        """Written before the list moved to read time; not the reporter's words."""
        order = _reported("น้ำมันไหล")
        older = order.model_copy(
            update={"reason": order.reason + " (เครื่องนี้มีใบงานเปิดอยู่แล้ว: WO-000011)"}
        )

        assert domain.reported_words(older) == "น้ำมันไหล"

    def test_a_ticket_that_is_not_a_report_comes_back_whole(self) -> None:
        order = _reported("น้ำมันไหล").model_copy(
            update={"origin": WorkOrderOrigin.CONDITION, "reason": "เกินเกณฑ์ 20 นาที"}
        )

        assert domain.reported_words(order) == "เกินเกณฑ์ 20 นาที"


class TestTheTitle:
    def test_is_machine_and_symptom_when_the_symptom_is_known(self) -> None:
        order = _reported("น้ำมันไหล")

        assert domain.title(order, "motor-overheat", WORDING) == "MC-001 มอเตอร์สายพานร้อนเกินกำหนด"

    def test_a_report_with_no_symptom_is_named_by_what_was_seen(self) -> None:
        order = _reported("น้ำมันไหลใต้ฐาน")

        assert domain.title(order, None, WORDING) == "MC-001 แจ้งว่า “น้ำมันไหลใต้ฐาน”"

    def test_the_reason_no_longer_carries_what_else_was_open(self) -> None:
        """Written once, it went on naming a closed ticket (finding 5)."""
        assert "เครื่องนี้มีใบงานเปิดอยู่แล้ว" not in _reported("น้ำมันไหล").reason

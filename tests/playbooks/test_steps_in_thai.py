"""ADR-095: the approver's Thai for each step, checked against the manual's figures.

A translation is where a torque of 42 becomes 24 and nobody notices, because
the reader trusts the numbers in the language they read fluently. So the figures
must match the step exactly, in both directions.
"""

from __future__ import annotations

import pytest

from pdm.contracts import DocumentId, PlaybookStep
from pdm.playbooks.service import in_thai, tools_in_thai

DOC = DocumentId("a" * 64)


def _step(text: str) -> PlaybookStep:
    return PlaybookStep(text=text, source_doc=DOC, page=5, confidence=0.9)


STEPS = (
    _step("Isolate the cabinet following the lockout procedure on page 2."),
    _step("Remove the four fan mounting screws torqued to 3 Nm."),
    _step("Restore power and confirm the fan reaches 1500 rpm within 30 seconds."),
)


def test_each_step_carries_its_thai_and_keeps_the_manuals_words() -> None:
    rendered = in_thai(
        STEPS,
        (
            "ตัดพลังงานตู้ควบคุมตามขั้นตอนล็อกเอาต์ในหน้า 2",
            "ถอดสกรูยึดพัดลมทั้งสี่ตัว (แรงบิด 3 Nm)",
            "จ่ายไฟกลับ แล้วตรวจว่าพัดลมหมุนถึง 1,500 rpm ภายใน 30 วินาที",
        ),
    )

    assert [step.text for step in rendered] == [step.text for step in STEPS]
    assert rendered[1].text_th == "ถอดสกรูยึดพัดลมทั้งสี่ตัว (แรงบิด 3 Nm)"
    assert all(step.page == 5 and step.source_doc == DOC for step in rendered)


def test_a_blank_entry_leaves_that_step_in_the_manuals_words() -> None:
    rendered = in_thai(STEPS, ("", "  ", "จ่ายไฟกลับ แล้วตรวจว่าหมุนถึง 1500 rpm ใน 30 วินาที"))

    assert rendered[0].text_th is None
    assert rendered[1].text_th is None
    assert rendered[2].text_th is not None


def test_a_changed_figure_is_refused_and_named() -> None:
    with pytest.raises(ValueError, match="ขั้นที่ 2") as refused:
        in_thai(STEPS, ("", "ถอดสกรูยึดพัดลม แรงบิด 8 Nm", ""))

    assert "ขาด 3" in str(refused.value)
    assert "เกิน 8" in str(refused.value)


def test_a_dropped_figure_is_refused_too() -> None:
    with pytest.raises(ValueError, match="ขาด 30"):
        in_thai(STEPS, ("", "", "จ่ายไฟกลับ แล้วตรวจว่าพัดลมหมุนถึง 1500 rpm"))


def test_the_count_must_line_up_with_the_steps() -> None:
    with pytest.raises(ValueError, match="ต้องแปลตามลำดับขั้นให้ครบ"):
        in_thai(STEPS, ("ขั้นเดียว",))


class TestUnitsTravelWithTheirFigures:
    """Red team (ADR-108): the figure check compared numbers only, so a torque
    of 3 Nm rendered as 3 มม. passed. A unit the manual states must come through
    the Thai unchanged, in either language's spelling."""

    def test_a_changed_unit_is_refused(self) -> None:
        with pytest.raises(ValueError, match="หน่วย"):
            in_thai(STEPS, ("", "ถอดสกรูยึดพัดลมสี่ตัว แรงบิด 3 มม.", ""))

    def test_a_dropped_unit_is_refused(self) -> None:
        with pytest.raises(ValueError, match="หน่วย"):
            in_thai(STEPS, ("", "ถอดสกรูยึดพัดลมสี่ตัว แรงบิด 3", ""))

    def test_the_unit_in_thai_words_is_accepted(self) -> None:
        rendered = in_thai(STEPS, ("", "ถอดสกรูยึดพัดลมสี่ตัว แรงบิด 3 นิวตันเมตร", ""))

        assert rendered[1].text_th == "ถอดสกรูยึดพัดลมสี่ตัว แรงบิด 3 นิวตันเมตร"

    def test_seconds_and_rpm_in_thai_are_accepted(self) -> None:
        rendered = in_thai(
            STEPS, ("", "", "จ่ายไฟกลับ แล้วตรวจว่าพัดลมหมุนถึง 1500 รอบต่อนาทีภายใน 30 วินาที")
        )

        assert rendered[2].text_th is not None


# ADR-130: the tools a technician fetches, under the same rule as the steps.
TOOLS = ("torque wrench 5-60 Nm", "belt tension gauge", "10 mm socket")


def test_each_tool_carries_its_thai_and_a_blank_keeps_the_manuals_words() -> None:
    assert tools_in_thai(TOOLS, ("ประแจวัดแรงบิด 5-60 Nm", "", "ลูกบ็อกซ์ 10 mm")) == (
        "ประแจวัดแรงบิด 5-60 Nm",
        "",
        "ลูกบ็อกซ์ 10 mm",
    )


def test_all_blank_is_no_rendering() -> None:
    assert tools_in_thai(TOOLS, ("", " ", "")) == ()


def test_a_tool_whose_range_changed_is_refused() -> None:
    """A wrench of 5-50 Nm is the wrong wrench."""
    with pytest.raises(ValueError, match="เครื่องมือรายการที่ 1"):
        tools_in_thai(TOOLS, ("ประแจวัดแรงบิด 5-50 Nm", "", ""))


def test_a_tool_whose_unit_was_dropped_is_refused() -> None:
    with pytest.raises(ValueError, match="หน่วย"):
        tools_in_thai(TOOLS, ("", "", "ลูกบ็อกซ์ 10 นิ้ว"))


def test_the_count_must_match() -> None:
    with pytest.raises(ValueError, match="3 รายการ"):
        tools_in_thai(TOOLS, ("ประแจ 5-60 Nm",))

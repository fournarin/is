"""โครงแพ็กเกจต้องตรงกับ docs-md/design.md 2 เสมอ

เทสต์นี้ไม่ได้ตรวจพฤติกรรม แต่ตรวจ **รูปทรง** — เพราะกฎใน .importlinter
อ้างชื่อโมดูลตรง ๆ ถ้ามีคนเปลี่ยนชื่อหรือลบโมดูลทิ้ง กฎที่อ้างชื่อนั้น
จะเงียบไปเฉย ๆ แทนที่จะล้ม ซึ่งแปลว่า ADR-003 และ ADR-030 จะหยุดถูกบังคับ
โดยไม่มีใครรู้

และการห้ามมีโมดูลนอกรายการ กันไม่ให้โครงค่อย ๆ งอกจนกฎ import ตามไม่ทัน
"""

import importlib
import pkgutil

import pdm
import pdm.workers

# ต้องตรงกับตารางใน design.md 2 — แก้ที่นี่ได้ก็ต่อเมื่อแก้เอกสารด้วย
EXPECTED_MODULES = frozenset(
    {
        "contracts",
        "platform",
        "signals",
        "triggers",
        "playbooks",
        "retrieval",
        "llm",
        "authoring",
        "work",
        "dispatch",
        "sinks",
        "sim",
        "api",
        "workers",
    }
)

# ADR-026 แยก worker เป็นสองบทบาทที่ต้องแยก process กันได้
EXPECTED_WORKER_ROLES = frozenset({"runtime", "authoring"})


def _submodules(package: object) -> frozenset[str]:
    path = getattr(package, "__path__", None)
    assert path is not None, f"{package} ไม่ใช่แพ็กเกจ"
    return frozenset(info.name for info in pkgutil.iter_modules(path))


def test_ทุกโมดูลใน_design_md_มีอยู่จริงและ_import_ได้() -> None:
    for name in sorted(EXPECTED_MODULES):
        importlib.import_module(f"pdm.{name}")


def test_ไม่มีโมดูลนอกรายการใน_design_md() -> None:
    assert _submodules(pdm) == EXPECTED_MODULES


def test_worker_มีสองบทบาทตาม_adr_026() -> None:
    assert _submodules(pdm.workers) == EXPECTED_WORKER_ROLES


def test_ทุกโมดูลมี_docstring_บอกหน้าที่() -> None:
    """โมดูลเปล่าที่ไม่บอกว่ามีไว้ทำอะไร คือร่องรอยที่ lessons_carried 4.4 เตือน"""
    for name in sorted(EXPECTED_MODULES):
        module = importlib.import_module(f"pdm.{name}")
        assert module.__doc__, f"pdm.{name} ไม่มี docstring บอกหน้าที่"

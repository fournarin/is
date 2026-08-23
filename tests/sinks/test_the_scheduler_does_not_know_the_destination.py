"""ADR-012's actual claim, asserted rather than described.

`.importlinter` enforces this on every push, and that is the gate that matters.
This file exists beside it for the reason `test_package_layout.py` exists beside
the other contracts: the linter refers to modules as literal strings, so a
renamed module leaves the rule green and enforcing nothing.

It also reads as the sentence ADR-012 is making. "The scheduler never learns
what the destination is" is a property of the source, and a property of the
source is testable without a linter's configuration in the way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SOURCE = Path("src/pdm")

# The two layers that must not know a destination exists. Not "must not import a
# concrete sink": importing the port would already be layer 3 knowing that
# somewhere to send things exists, and the failure worth preventing - a
# scheduler that starts ranking by whether a ticket was delivered - needs only
# the port (ADR-068).
BLIND = ("dispatch", "work")

# Where delivery is composed instead. Listed so that this test says where the
# knowledge is allowed to be, rather than only where it is not.
MAY_KNOW = ("workers", "api")


def _files(package: str) -> list[Path]:
    return sorted((SOURCE / package).rglob("*.py"))


@pytest.mark.parametrize("package", BLIND)
def test_a_layer_that_must_not_know_the_destination_does_not_name_it(package: str) -> None:
    found = [
        path
        for path in _files(package)
        if any(
            line.startswith(("from pdm.sinks", "import pdm.sinks"))
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    ]
    assert found == [], f"{package}/ imports pdm.sinks: {[str(p) for p in found]}"


@pytest.mark.parametrize("package", BLIND)
def test_the_package_is_there_to_be_imported_at_all(package: str) -> None:
    """Otherwise the test above passes on an empty directory, which is how a
    guard like this quietly stops meaning anything."""
    assert _files(package), f"{package}/ has no source files"


# The concrete sinks, by name. The ban above is on the package and is stronger,
# but #74 asks for this one specifically - and a class name can reach a module
# through a string, a factory or a comment that later becomes code, none of
# which an import linter sees.
CONCRETE = ("OwnSystemSink", "FileSink")


@pytest.mark.parametrize("package", BLIND)
def test_no_concrete_sink_is_named_there_either(package: str) -> None:
    for path in _files(package):
        body = path.read_text(encoding="utf-8")
        for name in CONCRETE:
            assert name not in body, f"{path} names {name}"


def test_the_import_contract_that_enforces_this_still_names_both_layers() -> None:
    """The linter's own configuration, checked for the thing a rename breaks."""
    config = Path(".importlinter").read_text(encoding="utf-8")

    assert "the-scheduler-does-not-know-the-destination" in config
    for package in BLIND:
        assert f"    pdm.{package}\n" in config


def test_somewhere_is_allowed_to_know() -> None:
    """A ban with nowhere on the other side of it would mean nothing delivers.

    The composition root is where layer 3 and layer 4 meet, and this is what
    makes the ban above a design rather than an omission (ADR-068).
    """
    composed = [
        path
        for package in MAY_KNOW
        for path in _files(package)
        if "pdm.sinks" in path.read_text(encoding="utf-8")
    ]
    assert composed, "nothing composes a sink, so no ticket can ever leave"

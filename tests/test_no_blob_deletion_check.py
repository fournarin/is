"""The gate that keeps ADR-019's "no code deletes a blob" true.

A gate with no test of its own is the worst kind of check: it reports success
whether or not it is looking at anything, and the thing it protects fails
silently by design. This one has two ways to pass while checking nothing - an
unmatched pattern and a source root that does not resolve - so both are tested
directly rather than inferred from the repository being clean.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_no_blob_deletion as gate

DELETIONS = [
    "os.remove(path)",
    "os.unlink(path)",
    "path.unlink()",
    "path.unlink(missing_ok=True)",
    "shutil.rmtree(directory)",
    "rmtree(directory)",
    "os.rmdir(directory)",
]

INNOCENT = [
    "document = repo.withdraw(conn, document_id, now=now)",
    "status = DocumentStatus.WITHDRAWN",
    "# withdrawing does not remove the file",
    'handle = path.open("rb")',
]


@pytest.fixture
def source_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "src" / "pdm"
    root.mkdir(parents=True)
    monkeypatch.setattr(gate, "SOURCE_ROOT", root)
    return root


@pytest.mark.parametrize("line", DELETIONS)
def test_every_way_of_removing_a_file_is_caught(
    source_tree: Path, line: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (source_tree / "somewhere.py").write_text(f"def clean():\n    {line}\n", encoding="utf-8")

    assert gate.main() == 1
    assert "ADR-019" in capsys.readouterr().out


@pytest.mark.parametrize("line", INNOCENT)
def test_withdrawing_a_document_is_not_a_deletion(source_tree: Path, line: str) -> None:
    """The gate must not make the correct way of doing this look wrong, or the
    next person routes around it."""
    (source_tree / "somewhere.py").write_text(f"def withdraw():\n    {line}\n", encoding="utf-8")

    assert gate.main() == 0


def test_the_escape_hatch_works_and_is_per_line(source_tree: Path) -> None:
    """The object store removes its own temporary file and nothing else. A
    file-level exemption would have let the same file delete a stored blob."""
    (source_tree / "store.py").write_text(
        "def put():\n"
        "    temporary.unlink(missing_ok=True)  # allow: temp-file\n"
        "    stored.unlink()\n",
        encoding="utf-8",
    )

    assert gate.main() == 1


def test_a_source_root_that_does_not_exist_fails_rather_than_passing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The failure mode that makes a gate worthless. Resolved from the working
    directory, this scanned nothing and exited 0 anywhere but the repository
    root - reporting success by finding no files to check."""
    monkeypatch.setattr(gate, "SOURCE_ROOT", tmp_path / "nowhere")

    assert gate.main() == 1
    assert "checked nothing" in capsys.readouterr().out


def test_the_real_source_tree_is_clean() -> None:
    assert gate.SOURCE_ROOT.is_dir()
    assert gate.main() == 0

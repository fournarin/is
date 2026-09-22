"""The documentation-link gate must catch a link that points at nothing.

`check_doc_links.py` was written because five citations in `docs/adr/` were
broken at once, and it is the only thing standing between the archive and that
happening again. It had no test: it had only ever been run against documentation
it passes, which is indistinguishable from a gate that matches no files, skips
every link, or was quietly narrowed to a directory nobody writes in.

The failure this guards against lands on the reader, not the author - a dead
link renders blue and 404s for whoever was handed the repository. So the gate
gets the same treatment as the invariants (#108): a tree with the violation
planted in it, and a requirement that the check reports it.
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_doc_links import REPO, check


def _docs(root: Path, name: str, body: str) -> Path:
    path = root / "docs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_the_real_documentation_resolves() -> None:
    broken, checked = check(REPO)
    assert broken == []
    assert checked > 100, (
        "the gate resolved almost nothing, which a repository with eighty "
        "cross-citing decision records cannot be true of: the glob has stopped "
        "matching, and a green result here now means nothing."
    )


def test_a_link_to_a_file_that_does_not_exist_is_caught(tmp_path: Path) -> None:
    _docs(tmp_path, "a.md", "See [the record](0099-a-record-nobody-wrote.md).\n")

    broken, checked = check(tmp_path)

    assert checked == 1
    assert len(broken) == 1
    assert "0099-a-record-nobody-wrote.md" in broken[0]


def test_the_report_names_the_file_and_the_line(tmp_path: Path) -> None:
    """Whoever has to fix it needs to be told where, not that.

    The original failure was five broken links across three records; a message
    that said only "some links are broken" would have sent somebody through
    eighty files by hand.
    """
    _docs(tmp_path, "b.md", "intro\n\nmore\n\n[ADR-080](0080-missing.md)\n")

    broken, _ = check(tmp_path)

    assert broken[0].strip().startswith("docs/b.md:5")


def test_a_link_that_resolves_is_not_reported(tmp_path: Path) -> None:
    _docs(tmp_path, "target.md", "the target\n")
    _docs(tmp_path, "a.md", "See [the target](target.md).\n")

    assert check(tmp_path) == ([], 1)


def test_an_anchor_on_a_file_that_exists_is_not_reported(tmp_path: Path) -> None:
    """Anchors are checked as far as the file, by design.

    Matching the heading inside it would turn the first failure into an argument
    about capitalisation, and ADR headings are prose.
    """
    _docs(tmp_path, "target.md", "# A heading\n")
    _docs(tmp_path, "a.md", "See [a heading](target.md#a-heading).\n")

    assert check(tmp_path) == ([], 1)


def test_an_anchor_on_a_file_that_does_not_exist_is_still_caught(tmp_path: Path) -> None:
    _docs(tmp_path, "a.md", "See [a heading](gone.md#a-heading).\n")

    broken, _ = check(tmp_path)

    assert len(broken) == 1


def test_external_links_are_not_followed(tmp_path: Path) -> None:
    """A gate that fails because a website was down is one people rerun.

    `https://example.invalid` cannot resolve to a file, and the check must not
    count it as a broken one - otherwise every record citing a standard or an
    issue would fail.
    """
    _docs(
        tmp_path,
        "a.md",
        "[issue](https://github.com/fournarin/is/issues/108) "
        "[site](http://example.invalid/x) [mail](mailto:nobody@example.com) "
        "[section](#known-gaps)\n",
    )

    assert check(tmp_path) == ([], 0)


def test_markdown_at_the_root_is_checked_too(tmp_path: Path) -> None:
    """`CLAUDE.md` and `README.md` carry the links a new reader follows first.

    They sit outside `docs/`, so a check that walked only `docs/` would leave
    the two most-read files in the repository uncovered.
    """
    (tmp_path / "README.md").write_text("[the plan](docs/gone.md)\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()

    broken, checked = check(tmp_path)

    assert checked == 1
    assert "README.md:1" in broken[0]

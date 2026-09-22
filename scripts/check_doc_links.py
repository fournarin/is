"""Every relative link in the documentation points at a file that exists.

The decision records are the design rationale and they cite each other
constantly - `docs/adr/README.md` says to read them in order, and a reader who
follows a citation into nothing has lost the thread the record was written to
give them. That is the whole value of an append-only archive: the argument is
distributed across it, held together by the citations.

This exists because five of them were broken at once, all in the three most
recently written records, and all in the same way: the link text named the right
record and the path named a file that had never existed. `ADR-080` cited
`0040-the-question-is-asked-in-the-requesters-words.md` where the file is
`0040-what-happens-when-somebody-asks-twice.md`. Both are reasonable names for
that record; only one of them is on disk. Nothing catches that by reading,
because the link text is correct and the URL is the part nobody looks at.

Markdown does not fail on a dead link. It renders, it is blue, and it 404s for
the reader and not for the author - so the failure lands on whoever is being
handed the repository rather than on whoever wrote it. The asymmetry is the
argument for a gate: the cost of the mistake falls on someone with no way to
notice it in advance.

Scope: relative links in `docs/**/*.md` and the repository's markdown at the
root. External links are not followed - a gate that fails because a website was
down is a gate people learn to rerun rather than read. Anchors (`#section`) are
checked as far as the file they name, not the heading inside it, because ADR
headings are prose and matching them would be a second-guessing exercise the
first failure would turn into a rule about capitalisation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# [text](target). Targets with whitespace are not links we can resolve and are
# left alone rather than guessed at.
LINK = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<target>[^)\s]+)\)")

SKIP_PREFIXES = ("http://", "https://", "mailto:", "#")


def _markdown_files(root: Path) -> list[Path]:
    files = sorted((root / "docs").rglob("*.md"))
    files += sorted(p for p in root.glob("*.md"))
    return files


def check(root: Path) -> tuple[list[str], int]:
    """Broken links under `root`, and how many links were resolved at all.

    `root` is a parameter rather than `REPO` so that the gate can be run against
    a tree containing a violation, which is the only way to find out that it
    still catches one (invariant-style test, #108). A checker that has only ever
    been run against documentation it passes is a checker nobody has seen refuse.

    The count comes back with the list because a green result that resolved zero
    links is the failure this gate cannot report on its own: a glob that stops
    matching passes exactly as loudly as documentation with no dead links in it.
    """
    broken: list[str] = []
    checked = 0

    for path in _markdown_files(root):
        text = path.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            target = match.group("target")
            if target.startswith(SKIP_PREFIXES):
                continue
            checked += 1
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            if resolved.exists():
                continue
            line = text.count("\n", 0, match.start()) + 1
            relative = path.relative_to(root)
            broken.append(f"  {relative}:{line}  [{match.group('text')}] -> {target}")

    return broken, checked


def main() -> int:
    broken, checked = check(REPO)

    if broken:
        print(f"Documentation links that point at nothing ({len(broken)} of {checked}):")
        print()
        print("\n".join(broken))
        print()
        print(
            "The link text is usually right and the path is usually invented. "
            "Check the filename in docs/adr/ rather than the record's title."
        )
        return 1

    print(f"{checked} relative links, all resolving.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

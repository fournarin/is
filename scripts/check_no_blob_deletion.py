"""Nothing in the application deletes a file (ADR-019).

ADR-019 states it as a property of the system: "the application contains no code
that deletes a blob". As an agreement that lasts until the first time the disk
fills up on a Friday. As a gate it is a build failure.

What it protects is not disk hygiene but evidence. A `playbook_snapshot` cites a
page in a specific edition, and a closed work order has to be able to prove what
the system instructed (ADR-018). A cleanup job that removes a PDF nothing
*appears* to reference destroys that proof silently - the work order still
renders, its citation still says "page 47", and there is no longer anything to
check it against.

This is why "delete" in this system is a change to `document.status` and why
ADR-019 has no cleanup job: if the volume fills, that is an operator decision
taken against a written procedure, not something a timer does at 3am.

Escape hatch: `# allow: temp-file` on a line that genuinely has to remove a file it
created itself, such as the object store discarding its own temporary upload.
Rare enough to be read every time it appears - and note the hatch is per line
rather than per file, because even the store must not delete a stored blob.

Not spelled `# noqa:`: that prefix belongs to ruff, which warns about codes it
does not recognise. A hatch that makes the linter complain is a hatch somebody
removes by deleting the comment rather than the call.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SOURCE_ROOT = Path("src/pdm")

BANNED = re.compile(
    r"""(
        \bos\.(remove|unlink|rmdir|removedirs)
      | \bshutil\.rmtree
      | \.unlink\s*\(
      | \brmtree\s*\(
      | \bPath\s*\([^)]*\)\.unlink
    )""",
    re.VERBOSE,
)

ESCAPE_HATCH = "allow: temp-file"


def main() -> int:
    violations: list[str] = []

    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BANNED.search(line) and ESCAPE_HATCH not in line:
                violations.append(f"{path}:{lineno}: {line.strip()}")

    if violations:
        print("File deletion in application code (ADR-019).")
        print(
            "A stored document is evidence behind a closed work order. Withdraw it "
            "by setting document.status instead:\n"
        )
        print("\n".join(violations))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

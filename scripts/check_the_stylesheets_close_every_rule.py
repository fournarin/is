"""Every rule in a stylesheet is closed, because nothing else here notices.

On 2026-08-23 the overview screen landed (#70) with `.page mark`'s closing brace
missing. Everything written after it - the line diagram, the shift band, the
held list, the confirmation panel, the report form, every style added by four
later slices - was swallowed into that rule and never applied. It survived three
and a half weeks and every gate in this repository, and it was found by accident
while adding a rule of its own.

Nothing catches it, and that is the point of this file:

  * `eslint .` reads JavaScript and TypeScript, not CSS;
  * `npm run build` compiles the stylesheet and recovers from the error rather
    than failing on it, so the web job stays green;
  * `npm test` covers the offline close queue;
  * the four `web/check-*.py` screen checks read content over HTTP. A screen with
    no styles serves exactly the same HTML as a screen with all of them, so they
    pass either way. That is not a gap in them - they assert on what a screen
    says, and what it *looks like* is not something an HTTP response can be asked.

So this is the smallest check that makes the whole class impossible, and it
deliberately depends on nothing: no CSS parser, no formatter, no new package
(`CLAUDE.md` - no new dependency without an ADR). Braces outside comments and
strings have to balance, and every rule has to be closed before the file ends.

It is a syntax check and not a style check. It has no opinion about how the file
is laid out, which is why it can be believed when it says something is wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

STYLESHEETS = sorted(Path("web").rglob("*.css"))

# Directories that hold somebody else's CSS, which is not ours to be right about.
SKIP = ("node_modules", ".next")


def unbalanced(text: str) -> list[str]:
    """Where the braces stop matching, reading the file the way a parser does.

    Comments and quoted strings are skipped, because a brace inside either is
    text rather than structure - `content: "}"` is valid and common.
    """
    problems: list[str] = []
    open_at: list[int] = []

    line = 1
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if char == "\n":
            line += 1
            index += 1
            continue

        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end == -1:
                problems.append(f"line {line}: a comment is never closed")
                break
            line += text.count("\n", index, end)
            index = end + 2
            continue

        if char in "\"'":
            quote = char
            index += 1
            while index < length and text[index] != quote:
                if text[index] == "\\":
                    index += 1
                elif text[index] == "\n":
                    # An unterminated string is its own error, and the line
                    # number of the opening quote is the useful one.
                    problems.append(f"line {line}: a {quote} string is never closed")
                    break
                index += 1
            index += 1
            continue

        if char == "{":
            open_at.append(line)
        elif char == "}":
            if not open_at:
                problems.append(f"line {line}: a closing brace with nothing open")
            else:
                open_at.pop()

        index += 1

    problems.extend(f"line {opened}: this rule is never closed" for opened in open_at)
    return problems


def main() -> int:
    violations: list[str] = []

    for path in STYLESHEETS:
        if any(part in SKIP for part in path.parts):
            continue
        for problem in unbalanced(path.read_text(encoding="utf-8")):
            violations.append(f"{path}: {problem}")

    if violations:
        print("A stylesheet does not close every rule it opens.")
        print("Everything after an unclosed rule is swallowed into it and never applies:\n")
        print("\n".join(violations))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

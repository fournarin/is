"""The gate that keeps every stylesheet rule closed.

A gate with no test of its own reports success whether or not it is looking at
anything, and what this one protects fails silently by design: a browser
recovers from an unclosed rule, `next build` recovers from it, and a screen with
no styles serves the same HTML as a screen with all of them.

The case at the top is the real one, reduced. `.page mark` lost its closing
brace in #70 and took the whole overview screen with it for three and a half
weeks.
"""

from __future__ import annotations

import pytest

from scripts import check_the_stylesheets_close_every_rule as gate

THE_REAL_ONE = """
.page mark {
  color: var(--ink);
  padding: 0.05rem 0;

/* ── the overview (slice 10.5) ── */

.line-scroll {
  overflow-x: auto;
}
"""

CLOSED = [
    ".a { color: red; }",
    ".a {\n  color: red;\n}\n\n.b {\n  color: blue;\n}\n",
    "@media (max-width: 30rem) {\n  .a {\n    color: red;\n  }\n}\n",
    ":root {\n  --x: 1;\n}\n",
]


class TestItCatchesTheThingItExistsFor:
    def test_the_rule_that_swallowed_the_overview_screen(self) -> None:
        problems = gate.unbalanced(THE_REAL_ONE)

        assert problems
        assert "never closed" in problems[0]

    def test_it_names_the_line_the_rule_opened_on_not_the_end_of_the_file(self) -> None:
        """A check that says "somewhere in this file" is one somebody reads
        once and then stops running."""
        problems = gate.unbalanced(THE_REAL_ONE)

        assert "line 2" in problems[0]

    def test_a_closing_brace_with_nothing_open_is_caught_too(self) -> None:
        problems = gate.unbalanced(".a { color: red; }\n}\n")

        assert problems == ["line 2: a closing brace with nothing open"]

    def test_a_comment_that_never_ends_is_caught(self) -> None:
        problems = gate.unbalanced(".a { color: red; }\n/* and then nothing\n")

        assert problems == ["line 2: a comment is never closed"]


class TestItDoesNotCryWolf:
    @pytest.mark.parametrize("stylesheet", CLOSED)
    def test_a_balanced_stylesheet_passes(self, stylesheet: str) -> None:
        assert gate.unbalanced(stylesheet) == []

    def test_a_brace_inside_a_comment_is_text_and_not_structure(self) -> None:
        assert gate.unbalanced("/* an example: .a { color: red } */\n.b { color: blue; }\n") == []

    def test_a_brace_inside_a_string_is_text_and_not_structure(self) -> None:
        """`content: "}"` is valid CSS and the reason this cannot be a `count`
        of two characters."""
        assert gate.unbalanced('.a::after {\n  content: "}";\n}\n') == []

    def test_an_escaped_quote_does_not_end_the_string(self) -> None:
        assert gate.unbalanced('.a::after {\n  content: "say \\" }";\n}\n') == []


class TestTheRepositoryItself:
    def test_every_stylesheet_that_ships_is_closed(self) -> None:
        """The check running over the real files, so that a stylesheet added
        later is covered without anybody remembering to add it here."""
        assert gate.main() == 0

    def test_it_is_actually_looking_at_something(self) -> None:
        """The failure mode of every gate in this directory: passing because it
        found no files to read."""
        assert gate.STYLESHEETS, "no stylesheets found - the gate would pass by looking at nothing"
        assert any(path.name == "globals.css" for path in gate.STYLESHEETS)

"""The seeder's default must not create an account whose password is on GitHub.

`scripts/seed_demo.py` is two things at once, and the tension is in its own
docstring: it is how a demo gets somebody to sign in as, and it is "the thing an
operator reruns on the plant's machine" (ADR-078 argues the second explicitly -
creating accounts is administration rather than fiction, which is why they are in
this script and an invented technician roster is not).

Those two readings want different passwords. `docker-compose.yml` publishes 8000
and 3000, `platform/auth/repo.py` has `set_password` with no endpoint reaching
it, and `docs/demo.md` prints all four passwords - so an installation seeded the
old way had four unchangeable accounts, one of them a supervisor who can confirm
work orders, with the credentials in a public repository.

The default now generates. `--demo-passwords` asks for the published ones by
name, which is what `rehearse.py` and `web/check-sign-in.py` do because they sign
in as those accounts.

These tests read the source rather than running the seeder, which needs a
database, a storage directory and the corpus. What is being protected is a
property of the code: that the published constant is not the default.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SEED = Path(__file__).resolve().parent.parent / "scripts" / "seed_demo.py"
PUBLISHED = ("demo-technician", "demo-engineer", "demo-supervisor", "demo-operator")


@pytest.fixture(scope="module")
def source() -> str:
    return SEED.read_text(encoding="utf-8")


class TestTheDefault:
    def test_the_flag_exists_and_is_opt_in(self, source: str) -> None:
        """`action="store_true"` is the whole security property in one word: the
        published passwords are reached by asking, never by omission."""
        assert '"--demo-passwords"' in source
        assert 'action="store_true"' in source

    def test_a_password_is_generated_with_a_cryptographic_source(self, source: str) -> None:
        assert "secrets.token_urlsafe" in source

    def test_the_generated_password_is_the_default_branch(self, source: str) -> None:
        """The conditional has to read "demo one only if asked". Written the
        other way round - `generated if not args.demo_passwords else ...` - it
        would pass every other test here and still be correct, but this is the
        line somebody edits under time pressure and the direction it faces is
        worth pinning."""
        tree = ast.parse(source)
        choices = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.IfExp) and "demo_passwords" in ast.unparse(node.test)
        ]
        assert choices, "no conditional choosing between a demo and a generated password"
        chosen = ast.unparse(choices[0])
        assert "token_urlsafe" in chosen
        assert chosen.index("demo_password") < chosen.index("token_urlsafe")


class TestThePublishedPasswordsAreStillReachable:
    """Removing them would break the rehearsal and every screen check, and the
    demo is a deliverable of its own (ADR-007, ADR-014)."""

    def test_all_four_are_still_in_the_table(self, source: str) -> None:
        for password in PUBLISHED:
            assert password in source

    def test_the_rehearsal_asks_for_them(self) -> None:
        rehearse = (SEED.parent / "rehearse.py").read_text(encoding="utf-8")
        assert "--demo-passwords" in rehearse

    def test_the_sign_in_check_says_it_needs_them(self) -> None:
        check = SEED.parent.parent / "web" / "check-sign-in.py"
        assert "--demo-passwords" in check.read_text(encoding="utf-8")


class TestWhatTheOperatorIsTold:
    def test_the_generated_case_says_the_password_cannot_be_recovered(self, source: str) -> None:
        """There is no way to display or change it afterwards. An operator who
        does not write it down at this moment has to recreate the account in the
        database by hand, and this is the only moment anything can say so."""
        assert "shown once" in source
        assert "change them" in source

    def test_the_demo_case_says_not_to_leave_the_accounts_behind(self, source: str) -> None:
        assert "nothing to lose" in source

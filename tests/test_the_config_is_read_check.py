"""The unread-configuration gate, including the false pass it admits to.

`config/policy.yaml` is the file an operator is told to edit, and every key in
it is a promise that editing it changes something (lesson 4.4). This gate keeps
that promise honest, and it had no test - so nothing said whether it would still
refuse a key nothing reads, or whether its globs had stopped matching.

The second half is the more interesting one. The check counts a field as read if
its name appears anywhere outside the schema, which means an identifier that
merely shares the name counts too. `safety_critical` passed on exactly that
coincidence for as long as nothing called `work/thresholds.propose`. The
docstring says so; #108 asks for the fixture that demonstrates it, because a
limitation written in prose beside a green gate is a limitation people stop
reading. `test_a_parameter_of_the_same_name_is_counted_as_a_read` plants it, and
it is written to pass: it records what the gate does, not what it should do.

Whether to tighten this to an AST-level read - the name must appear as an
attribute access on a config object - is a decision for a person, and is entry
in `docs/decisions-to-defend.md` rather than a change made here.
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_config_is_read import (
    ALLOWED_WITHOUT_A_READER,
    REPO,
    SCHEMA,
    SELF,
    _schema_fields,
    unread_fields,
)

SCHEMA_BODY = '''
"""A schema small enough to reason about."""

from pydantic import BaseModel


class Dispatch(BaseModel):
    model_config = {"frozen": True}
    version: int = 1

    load_ceiling: float
    fallback_minutes: int
'''


def _tree(tmp_path: Path, *, sources: dict[str, str]) -> Path:
    schema = tmp_path / "schema.py"
    schema.write_text(SCHEMA_BODY, encoding="utf-8")
    for relative, body in sources.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    for directory in ("src", "scripts", "web"):
        (tmp_path / directory).mkdir(exist_ok=True)
    return schema


# ── the gate refuses what it says it refuses ──────────────────────────────


def test_a_field_nothing_names_is_caught(tmp_path: Path) -> None:
    schema = _tree(
        tmp_path,
        sources={"src/pdm/dispatch.py": "def go(config):\n    return config.load_ceiling\n"},
    )

    assert unread_fields(schema, tmp_path) == [("fallback_minutes", "Dispatch")]


def test_the_report_names_the_class_that_declares_it(tmp_path: Path) -> None:
    """An operator sent to find `fallback_minutes` needs to know which section.

    `policy.yaml` is nested, and the same word can be a key under more than one
    heading.
    """
    schema = _tree(tmp_path, sources={})

    assert [owner for _, owner in unread_fields(schema, tmp_path)] == ["Dispatch", "Dispatch"]


def test_a_field_read_only_by_the_schema_itself_does_not_count(tmp_path: Path) -> None:
    """Declaring a field is not reading it.

    Without this exclusion every field would pass trivially, because every field
    is named in the module that declares it.
    """
    schema = _tree(tmp_path, sources={})

    assert len(unread_fields(schema, tmp_path)) == 2


def test_a_reader_deep_inside_src_is_found(tmp_path: Path) -> None:
    """`src/**/*.py`, not `src/*.py`. Nothing lives at the top of `src/`."""
    schema = _tree(
        tmp_path,
        sources={
            "src/pdm/dispatch/domain/score.py": (
                "def score(load_ceiling, fallback_minutes):\n    return 0\n"
            )
        },
    )

    assert unread_fields(schema, tmp_path) == []


def test_a_file_named_in_exclude_is_not_counted_as_a_reader(tmp_path: Path) -> None:
    """The gate excludes itself, and this is the mechanism that does it.

    It names every allowed exception twice, in the list and in the reason beside
    it, so a gate that read itself would pass by describing the problem.
    """
    excluded = tmp_path / "scripts" / "the_gate.py"
    schema = _tree(
        tmp_path,
        sources={
            "scripts/the_gate.py": "ALLOWED = {'load_ceiling', 'fallback_minutes'}\n",
        },
    )

    assert unread_fields(schema, tmp_path) == []
    assert len(unread_fields(schema, tmp_path, exclude=(excluded,))) == 2


def test_structure_is_not_configuration(tmp_path: Path) -> None:
    """`model_config` and `version` are pydantic's, not an operator's.

    Listing them would mean adding two permanent exceptions to every schema
    class, and an exception list nobody can empty is one nobody reads.
    """
    schema = _tree(tmp_path, sources={})

    assert {name for name, _ in unread_fields(schema, tmp_path)} == {
        "load_ceiling",
        "fallback_minutes",
    }


# ── the false pass, planted on purpose ────────────────────────────────────


def test_a_parameter_of_the_same_name_is_counted_as_a_read(tmp_path: Path) -> None:
    """**This test asserts the limitation, not the fix.**

    `fallback_minutes` here is a parameter of a function nothing calls. No
    configured value reaches it; the word merely occurs. The gate passes, and
    that is what `safety_critical` did for as long as nothing called
    `work/thresholds.propose`.

    A green `check_config_is_read.py` therefore means "every field's name occurs
    somewhere", which is a weaker claim than the file's title. Tightening it to
    an attribute read on a config object is the open decision; until somebody
    takes it, this is the shape of what the gate lets through, written where it
    fails if the gate is ever tightened.
    """
    schema = _tree(
        tmp_path,
        sources={
            "src/pdm/work/thresholds.py": (
                "def propose(counted, fallback_minutes, load_ceiling):\n"
                "    '''Nothing outside the tests calls this.'''\n"
                "    return counted\n"
            )
        },
    )

    assert unread_fields(schema, tmp_path) == []


def test_a_field_named_only_in_a_comment_is_counted_as_a_read(tmp_path: Path) -> None:
    """The same looseness, at its widest.

    A field mentioned in a comment and read nowhere passes. This is the cheapest
    demonstration that the gate matches text rather than data flow, and it is
    here so that nobody has to take the docstring's word for it.
    """
    schema = _tree(
        tmp_path,
        sources={
            "src/pdm/dispatch.py": (
                "def go(config):\n"
                "    # TODO: honour load_ceiling and fallback_minutes one day\n"
                "    return None\n"
            )
        },
    )

    assert unread_fields(schema, tmp_path) == []


# ── against the real schema ───────────────────────────────────────────────


def test_the_real_schema_has_no_unread_field_beyond_the_listed_exception() -> None:
    unread = {name for name, _ in unread_fields(SCHEMA, REPO, exclude=(SELF,))}

    assert unread == ALLOWED_WITHOUT_A_READER


def test_the_real_schema_is_actually_being_parsed() -> None:
    """A schema parse that silently found nothing would pass everything.

    `_schema_fields` reads module-level classes only. A refactor that nested the
    settings classes inside another class would return an empty mapping, and the
    gate would report success over nothing at all.
    """
    assert len(_schema_fields(SCHEMA)) > 50

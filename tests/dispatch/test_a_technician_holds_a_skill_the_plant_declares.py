"""Invariant 13's technician half, which was enforced nowhere until ADR-084.

`docs/invariants.md` cited boot validation for this and the loader never looked.
`add_technician` wrote whatever it was handed, and a label outside the
vocabulary fails in the quietest way the system has: `Technician.can_perform`
never matches, so that person is passed over by every round, and no screen, log
or round report says why. Nobody reports a bug that looks like being off the
roster.

The refusal is at the write, because that is the only place a vocabulary is in
reach: `contracts/` cannot read configuration (invariant 10 keeps it frozen and
free of I/O), and by the time `dispatch()` runs, the wrong label is already in
the table and looks exactly like a technician who cannot do the work.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from psycopg import Connection, connect

from pdm.contracts import SkillId, Technician, UserId
from pdm.dispatch import repo as dispatch_repo
from pdm.dispatch.repo import SkillNotInTheVocabulary

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
VOCABULARY = frozenset({SkillId("robot_mechanical"), SkillId("electrical")})
ANA = UserId("tech-ana")


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute("TRUNCATE technician CASCADE")
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _rows(conn: Connection[Any]) -> list[str]:
    return [str(row[0]) for row in conn.execute("SELECT user_id FROM technician").fetchall()]


class TestASkillOutsideTheVocabularyIsRefused:
    def test_a_typo_in_a_skill_label_is_refused_rather_than_stored(
        self, conn: Connection[Any]
    ) -> None:
        """`robot_mechanic` for `robot_mechanical`. Stored, it produces a
        technician who is on shift, available, and matched to nothing."""
        with pytest.raises(SkillNotInTheVocabulary, match="robot_mechanic"):
            dispatch_repo.add_technician(
                conn,
                Technician(user=ANA, skills=frozenset({SkillId("robot_mechanic")})),
                known_skills=VOCABULARY,
                now=NOW,
            )

        assert _rows(conn) == []

    def test_the_refusal_names_what_the_plant_does_declare(self, conn: Connection[Any]) -> None:
        """A refusal that does not say what the alternatives were is one
        somebody works around by removing the skill."""
        with pytest.raises(SkillNotInTheVocabulary, match="electrical, robot_mechanical"):
            dispatch_repo.add_technician(
                conn,
                Technician(user=ANA, skills=frozenset({SkillId("hydraulics")})),
                known_skills=VOCABULARY,
                now=NOW,
            )

    def test_one_bad_label_among_good_ones_is_still_refused(self, conn: Connection[Any]) -> None:
        with pytest.raises(SkillNotInTheVocabulary, match="hydraulics"):
            dispatch_repo.add_technician(
                conn,
                Technician(
                    user=ANA,
                    skills=frozenset({SkillId("electrical"), SkillId("hydraulics")}),
                ),
                known_skills=VOCABULARY,
                now=NOW,
            )

        assert _rows(conn) == []

    def test_an_empty_vocabulary_refuses_every_label(self, conn: Connection[Any]) -> None:
        """Deliberately not the stand-down `PlaybookStore` does (ADR-084 §3).
        A plant declaring no skills has no vocabulary for a label to be in, and
        `seed_demo_roster.py` already refuses to write a roster for one."""
        with pytest.raises(SkillNotInTheVocabulary, match="no skills at all"):
            dispatch_repo.add_technician(
                conn,
                Technician(user=ANA, skills=frozenset({SkillId("electrical")})),
                known_skills=frozenset(),
                now=NOW,
            )


class TestWhatTheCheckDoesNotRefuse:
    def test_every_label_in_the_vocabulary_is_written(self, conn: Connection[Any]) -> None:
        dispatch_repo.add_technician(
            conn,
            Technician(user=ANA, skills=VOCABULARY),
            known_skills=VOCABULARY,
            now=NOW,
        )

        assert _rows(conn) == [str(ANA)]

    def test_a_technician_with_no_skills_at_all_is_written(self, conn: Connection[Any]) -> None:
        """An apprentice holds no labels yet. That is a person the roster can
        carry, not a vocabulary error, and dispatch will simply not match them
        to work that names a skill."""
        dispatch_repo.add_technician(
            conn,
            Technician(user=ANA, skills=frozenset()),
            known_skills=frozenset(),
            now=NOW,
        )

        assert _rows(conn) == [str(ANA)]

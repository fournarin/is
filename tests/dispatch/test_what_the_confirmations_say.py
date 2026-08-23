"""What the confirmation record says about turning the switch (ADR-075, #81).

ADR-071 §8 collects the record and deliberately stops there: no threshold, and
no reading. This file holds the reading to the shape ADR-075 fixed, and five of
its tests are the ones that would fail if any part of the argument were dropped:

  * `TestTheThreeEndingsStaySeparate` - an expiry is an argument about the
    confirmation step and a rejection is an argument about the score. Collapsed
    into "not confirmed" they hide the strongest reason there is to turn the
    switch to `automatic`.
  * `TestAnExpiryIsNotADecisionTime` - `decided_at` on an expired row is the
    sweep noticing, not a person answering. Averaged in, it makes the shift lead
    look slow at exactly the moments nobody was there at all.
  * `TestRejectionsAndExpiriesAreListedInFull` - a count answers "how often" and
    the reasons answer "about what". The second is the half a person can act on.
  * `TestNothingIsDividedByNothing` - a share over an empty set is absent, never
    zero. "Nobody has confirmed anything" and "no proposal has been answered
    yet" are opposite findings and one of them is not evidence at all.
  * `TestTheReportSaysWhatItCannotSay` - a confirmation is not proof the
    placement was right, and the record is structurally silent about the mode it
    would be used to argue for (ADR-075 §5).

Pure by construction: `agreement()` takes proposals and returns a reading, so
every case here is written out by hand (invariant 10, ADR-030).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from pdm.contracts import Assignee, AssigneeRole, Role, ShiftId, UserId
from pdm.dispatch.agreement import WHAT_THE_RECORD_CANNOT_SAY, agreement
from pdm.dispatch.domain import Band
from pdm.dispatch.proposals import Proposal, ProposalState

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
TODAY = date(2026, 3, 3)
AFTERNOON = ShiftId("afternoon")
MORNING = ShiftId("morning")
SUP = UserId("sup-1")
CREW = (Assignee(user=UserId("tech-1"), role=AssigneeRole.PRIMARY),)


def _proposal(
    ref: str,
    *,
    state: ProposalState = ProposalState.PENDING,
    proposed_at: datetime = NOW,
    took_minutes: float | None = None,
    reason: str | None = None,
    band: Band | None = Band.NORMAL,
    shift_id: ShiftId | None = AFTERNOON,
    score: float = 1.0,
) -> Proposal:
    """One row of the record, written out rather than produced by a round."""
    decided_at = (
        None
        if state is ProposalState.PENDING
        else proposed_at + timedelta(minutes=took_minutes or 0)
    )
    person = state in (ProposalState.CONFIRMED, ProposalState.REJECTED)
    return Proposal(
        work_order_ref=ref,
        proposed_at=proposed_at,
        assignees=CREW,
        priority_score=score,
        priority_reason="high severity at the bottleneck",
        band=band,
        load_ratio=0.4 if band is not None else None,
        shift_id=shift_id,
        on_date=TODAY if shift_id is not None else None,
        state=state,
        decided_at=decided_at,
        decided_by=SUP if person else None,
        decided_role=Role.SUPERVISOR if person else None,
        reason=reason,
    )


class TestTheThreeEndingsStaySeparate:
    def test_each_ending_is_counted_as_itself(self) -> None:
        report = agreement(
            [
                _proposal("WO-1", state=ProposalState.CONFIRMED, took_minutes=2),
                _proposal("WO-2", state=ProposalState.REJECTED, took_minutes=3, reason="on leave"),
                _proposal("WO-3", state=ProposalState.EXPIRED, took_minutes=30),
                _proposal("WO-4"),
            ]
        )

        assert report.overall.proposed == 4
        assert report.overall.confirmed == 1
        assert report.overall.rejected == 1
        assert report.overall.expired == 1
        assert report.overall.pending == 1

    def test_a_pending_proposal_is_not_settled(self) -> None:
        """It is a question still open, and counting it as an ending would make
        a screen somebody has not reached yet look like a decision they made."""
        report = agreement([_proposal("WO-1"), _proposal("WO-2")])

        assert report.overall.pending == 2
        assert report.overall.settled == 0
        assert report.overall.answered == 0

    def test_agreement_is_measured_over_what_a_person_answered(self) -> None:
        """Not over everything proposed. An expiry is nobody's opinion about the
        placement, and dividing by it would report disagreement that was never
        expressed."""
        report = agreement(
            [
                _proposal("WO-1", state=ProposalState.CONFIRMED, took_minutes=1),
                _proposal("WO-2", state=ProposalState.CONFIRMED, took_minutes=1),
                _proposal("WO-3", state=ProposalState.REJECTED, took_minutes=1, reason="busy"),
                _proposal("WO-4", state=ProposalState.EXPIRED, took_minutes=30),
                _proposal("WO-5"),
            ]
        )

        assert report.overall.answered == 3
        assert report.overall.confirmed_share == pytest.approx(2 / 3)

    def test_the_expired_share_is_measured_over_everything_that_ended(self) -> None:
        """ADR-071 §8's second question: how much was never answered at all. Its
        denominator is every proposal that reached an ending, because that is the
        set a supervisor could have reached in time and did not."""
        report = agreement(
            [
                _proposal("WO-1", state=ProposalState.CONFIRMED, took_minutes=1),
                _proposal("WO-2", state=ProposalState.EXPIRED, took_minutes=30),
                _proposal("WO-3", state=ProposalState.EXPIRED, took_minutes=30),
                _proposal("WO-4", state=ProposalState.EXPIRED, took_minutes=30),
            ]
        )

        assert report.overall.settled == 4
        assert report.overall.expired_share == pytest.approx(0.75)


class TestAnExpiryIsNotADecisionTime:
    def test_the_sweep_is_left_out_of_the_time_a_person_took(self) -> None:
        """`decided_at` on an expired row is the window closing, not somebody
        deciding. It is always the full window, so averaging it in would drag
        every figure towards the expiry setting and away from the measurement."""
        report = agreement(
            [
                _proposal("WO-1", state=ProposalState.CONFIRMED, took_minutes=2),
                _proposal("WO-2", state=ProposalState.REJECTED, took_minutes=4, reason="no"),
                _proposal("WO-3", state=ProposalState.EXPIRED, took_minutes=30),
            ]
        )

        assert report.decision_time.answered == 2
        assert report.decision_time.median_minutes == pytest.approx(3.0)
        assert report.decision_time.longest_minutes == pytest.approx(4.0)

    def test_a_rejection_is_timed_as_well_as_a_confirmation(self) -> None:
        """Both are a person reading a screen and pressing something. Timing only
        the agreements would measure how long agreeing takes, which is a
        different question from how long deciding takes."""
        report = agreement(
            [_proposal("WO-1", state=ProposalState.REJECTED, took_minutes=6, reason="on leave")]
        )

        assert report.decision_time.answered == 1
        assert report.decision_time.mean_minutes == pytest.approx(6.0)


class TestRejectionsAndExpiriesAreListedInFull:
    def test_every_rejection_carries_its_reason_and_its_round(self) -> None:
        """The issue asks for the rejections in full. A reason detached from the
        band and the shift it was written against cannot be read six weeks later:
        "not now" means one thing on a heavy shift and another on a quiet one."""
        report = agreement(
            [
                _proposal(
                    "WO-2",
                    state=ProposalState.REJECTED,
                    took_minutes=5,
                    reason="ana is on the line stop, not free until 16:00",
                    band=Band.HEAVY,
                ),
                _proposal("WO-1", state=ProposalState.CONFIRMED, took_minutes=1),
            ]
        )

        (rejection,) = report.rejections
        assert rejection.work_order_ref == "WO-2"
        assert rejection.reason == "ana is on the line stop, not free until 16:00"
        assert rejection.band == Band.HEAVY
        assert rejection.shift_id == AFTERNOON
        assert rejection.decided_by == SUP
        assert rejection.decided_role is Role.SUPERVISOR
        assert rejection.minutes_to_decide == pytest.approx(5.0)

    def test_every_expiry_is_listed_too(self) -> None:
        """As loudly as the rejections, and for the same reason: a queue with a
        person-shaped hole in it is a finding, and a bare count of it is one a
        reader cannot check (ADR-071 §8)."""
        report = agreement(
            [
                _proposal("WO-9", state=ProposalState.EXPIRED, took_minutes=30, band=Band.HEAVY),
                _proposal("WO-1", state=ProposalState.CONFIRMED, took_minutes=1),
            ]
        )

        (expiry,) = report.expiries
        assert expiry.work_order_ref == "WO-9"
        assert expiry.band == Band.HEAVY
        assert expiry.shift_id == AFTERNOON
        assert expiry.expired_at == NOW + timedelta(minutes=30)
        assert expiry.waited_minutes == pytest.approx(30.0)

    def test_the_lists_are_in_the_order_they_happened(self) -> None:
        report = agreement(
            [
                _proposal(
                    "WO-2",
                    state=ProposalState.REJECTED,
                    proposed_at=NOW + timedelta(minutes=10),
                    took_minutes=1,
                    reason="second",
                ),
                _proposal("WO-1", state=ProposalState.REJECTED, took_minutes=1, reason="first"),
            ]
        )

        assert [one.reason for one in report.rejections] == ["first", "second"]


class TestPerShiftAndPerBand:
    def test_the_shifts_are_reported_apart(self) -> None:
        """ "The shift lead disagrees on the afternoon" and "the shift lead
        disagrees" are different findings, and only one of them is actionable."""
        report = agreement(
            [
                _proposal("WO-1", state=ProposalState.CONFIRMED, took_minutes=1, shift_id=MORNING),
                _proposal(
                    "WO-2",
                    state=ProposalState.REJECTED,
                    took_minutes=1,
                    reason="no",
                    shift_id=AFTERNOON,
                ),
                _proposal(
                    "WO-3",
                    state=ProposalState.REJECTED,
                    took_minutes=1,
                    reason="no",
                    shift_id=AFTERNOON,
                ),
            ]
        )

        by_shift = {segment.key: segment for segment in report.by_shift}
        assert by_shift["morning"].counts.confirmed_share == pytest.approx(1.0)
        assert by_shift["afternoon"].counts.confirmed_share == pytest.approx(0.0)
        assert by_shift["afternoon"].counts.rejected == 2

    def test_the_bands_are_reported_apart(self) -> None:
        """ADR-011's two bands are two different shifts to be a shift lead on,
        and agreement on a quiet one says nothing about agreement on a busy one."""
        report = agreement(
            [
                _proposal("WO-1", state=ProposalState.CONFIRMED, took_minutes=1, band=Band.NORMAL),
                _proposal(
                    "WO-2",
                    state=ProposalState.REJECTED,
                    took_minutes=1,
                    reason="no",
                    band=Band.HEAVY,
                ),
            ]
        )

        by_band = {segment.key: segment for segment in report.by_band}
        assert by_band["normal"].counts.confirmed == 1
        assert by_band["heavy"].counts.rejected == 1

    def test_a_proposal_with_no_band_is_reported_rather_than_dropped(self) -> None:
        """A round with no capacity to compute a ratio from records no band
        (ADR-045 §3). Dropping those rows would make the segments disagree with
        the total, and a reader who noticed would not know which was wrong."""
        report = agreement(
            [
                _proposal("WO-1", state=ProposalState.CONFIRMED, took_minutes=1),
                _proposal(
                    "WO-2",
                    state=ProposalState.CONFIRMED,
                    took_minutes=1,
                    band=None,
                    shift_id=None,
                ),
            ]
        )

        assert sum(segment.counts.proposed for segment in report.by_band) == 2
        assert sum(segment.counts.proposed for segment in report.by_shift) == 2
        assert [segment.key for segment in report.by_band][-1] is None
        assert [segment.key for segment in report.by_shift][-1] is None


class TestNothingIsDividedByNothing:
    def test_an_empty_record_reports_absence_rather_than_zeros(self) -> None:
        report = agreement([])

        assert report.overall.proposed == 0
        assert report.overall.confirmed_share is None
        assert report.overall.expired_share is None
        assert report.decision_time.median_minutes is None
        assert report.rejections == ()
        assert report.expiries == ()

    def test_a_record_with_nothing_answered_has_no_agreement_figure(self) -> None:
        """Three expiries and no answers is a strong finding about the
        confirmation step and no finding at all about the score."""
        report = agreement(
            [
                _proposal("WO-1", state=ProposalState.EXPIRED, took_minutes=30),
                _proposal("WO-2", state=ProposalState.EXPIRED, took_minutes=30),
                _proposal("WO-3", state=ProposalState.EXPIRED, took_minutes=30),
            ]
        )

        assert report.overall.confirmed_share is None
        assert report.overall.expired_share == pytest.approx(1.0)
        assert report.decision_time.answered == 0
        assert report.decision_time.mean_minutes is None


class TestTheReportSaysWhatItCannotSay:
    def test_the_limitation_is_carried_on_every_report(self) -> None:
        """Carried on the reading rather than left in the ADR, for ADR-073 §6's
        reason: a caveat that lives only in a document is absent at the moment
        somebody is looking at a number."""
        assert agreement([]).limitation == WHAT_THE_RECORD_CANNOT_SAY
        assert "automatic" in WHAT_THE_RECORD_CANNOT_SAY

    def test_the_reading_proposes_nothing(self) -> None:
        """ADR-071 §8 refuses to put a number in `policy.yaml` deciding when a
        plant may stop reviewing its own work orders, and this slice is the
        measuring rather than the deciding. A field a screen could render as a
        recommendation is the shape that refusal takes in code."""
        report = agreement([_proposal("WO-1", state=ProposalState.CONFIRMED, took_minutes=1)])

        assert not [
            name
            for name in report.model_dump()
            if any(word in name for word in ("recommend", "threshold", "switch", "verdict"))
        ]

"""The rule engine with a database behind it: signals in, Findings out.

State is loaded once per batch and the evaluation itself stays pure (ADR-042):
this module is the joining, and everything that decides anything is next door in
`domain.py` where it can be tested in a line.

It opens no connection. The caller supplies one, so a Finding and the work order
it produces commit together (ADR-017) - which is what stops a Finding existing
with nothing behind it, and a ticket referring to a Finding that was rolled back.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from datetime import timedelta
from typing import Any

from psycopg import Connection
from pydantic import BaseModel, ConfigDict

from pdm.contracts import FindingRef, MachineId, MachineModel, RuleId, Signal
from pdm.platform.clock import Clock
from pdm.platform.config.schema import RuleConfig
from pdm.triggers import repo
from pdm.triggers.domain import Debounce, Decision, Outcome, evaluate, forecast
from pdm.triggers.repo import AlreadyLive
from pdm.triggers.trend import Window


class Raised(BaseModel):
    """A Finding that was written, with what it superseded if anything."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_ref: FindingRef
    decision: Decision
    superseded: FindingRef | None = None


class Observation(BaseModel):
    """What one batch of signals did. Every outcome, not only the raised ones.

    The counts are the false-alarm picture: a rule that is suppressed a thousand
    times an hour and a rule that fires once are different problems, and a return
    value holding only the Findings would make them look the same (ADR-023's
    note about occurrence_count, one level up).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    raised: tuple[Raised, ...] = ()
    # Predicted Findings, kept apart from detections in the count. "Twelve
    # Findings this shift" means something different if eleven are forecasts,
    # and ADR-020's accuracy work needs the two separable anyway.
    forecast: tuple[Raised, ...] = ()
    repeated: int = 0
    suppressed: int = 0
    in_cooldown: int = 0
    quiet: int = 0
    # A repeat that wrote nothing, or a raise another worker got to first. Both
    # are the system working; both are also the shape of a bug, so they are
    # counted rather than swallowed.
    lost_races: int = 0

    @property
    def anything_happened(self) -> bool:
        return bool(self.raised) or bool(self.forecast) or bool(self.repeated)


class Triggers:
    """One rule engine, one clock, one set of rules.

    Holds the debounce between calls, which is the only state layer 1 has: a
    restart forgets how long an excess has held and the rule's clock starts
    again, once, up to `for_seconds` late (ADR-042 section 1).
    """

    def __init__(
        self,
        clock: Clock,
        rules: Iterable[RuleConfig],
        *,
        cooldown: timedelta,
        eta_grace: timedelta,
        model_of: Callable[[MachineId], MachineModel] | None = None,
        trend_window: timedelta | None = None,
        trend_min_samples: int = 10,
        trend_eta_error: Sequence[tuple[float, float]] = (),
        trend_horizon: timedelta | None = None,
    ) -> None:
        self.clock = clock
        self.rules = list(rules)
        # Which model a machine is, from config. Without it a rule declared for
        # one model fires on another emitting the same tag - a symptom code with
        # no playbook for that machine, and a threshold from a different one.
        # Optional only so a test can drive the engine with one model's rules.
        self.model_of = model_of
        # From policy.yaml, never from code: ADR-023's last consequence is that
        # these two live in configuration.
        self.cooldown = cooldown
        self.eta_grace = eta_grace
        self.debounce = Debounce()
        # The trend's own memory, alongside the debounce and forgotten the same
        # way (ADR-042 section 1). Prediction is off when no window is given,
        # which is what the detection-only tests use: a mechanism that could not
        # be turned off would have to be reasoned about in every test of the
        # other half.
        self.windows = Window(trend_window) if trend_window else None
        self.trend_min_samples = trend_min_samples
        self.trend_eta_error = tuple(trend_eta_error)
        self.trend_horizon = trend_horizon or timedelta(hours=24)

    def observe(
        self,
        conn: Connection[Any],
        signals: Iterable[Signal],
        *,
        under_repair: Mapping[MachineId, frozenset[RuleId]] | None = None,
    ) -> Observation:
        """Run a batch of signals through the rules and apply what they say.

        The lifecycle state is read once at the start rather than per signal. A
        plant's worth of channels at a sample a minute would otherwise be a query
        a second, to answer a question whose answer changes a few times an hour -
        and the in-memory copy is corrected as this batch raises Findings, so a
        rule that fires twice inside one batch still produces one record.
        """
        now = self.clock.now()
        open_findings = repo.live(conn)
        resolved_at = repo.last_resolved(conn)

        raised: list[Raised] = []
        predicted: list[Raised] = []
        counts = {Outcome.REPEAT: 0, Outcome.SUPPRESSED: 0, Outcome.IN_COOLDOWN: 0}
        quiet = 0
        lost = 0

        for signal in signals:
            decisions = evaluate(
                signal,
                self.rules,
                machine_model=self.model_of(signal.machine_id) if self.model_of else None,
                now=now,
                debounce=self.debounce,
                open_findings=open_findings,
                resolved_at=resolved_at,
                under_repair=under_repair or {},
                cooldown=self.cooldown,
            )
            if self.windows is not None:
                decisions += forecast(
                    signal,
                    self.rules,
                    machine_model=self.model_of(signal.machine_id) if self.model_of else None,
                    now=now,
                    windows=self.windows,
                    open_findings=open_findings,
                    resolved_at=resolved_at,
                    cooldown=self.cooldown,
                    horizon=self.trend_horizon,
                    min_samples=self.trend_min_samples,
                    eta_error=self.trend_eta_error,
                )

            for decision in decisions:
                if decision.outcome is Outcome.QUIET:
                    quiet += 1
                elif decision.outcome is Outcome.REPEAT and decision.finding is not None:
                    # A forecast seen again is a *newer forecast*: the fit moved,
                    # and the record has to move with it or a technician reads a
                    # crossing time computed from data six hours stale.
                    predicted_again = decision.finding
                    assert predicted_again.eta is not None
                    assert predicted_again.eta_confidence is not None
                    if repo.refresh_prediction(
                        conn,
                        machine_id=decision.machine_id,
                        rule_id=decision.rule_id,
                        eta=predicted_again.eta,
                        eta_confidence=predicted_again.eta_confidence,
                        evidence=predicted_again.evidence,
                        now=now,
                    ):
                        counts[Outcome.REPEAT] += 1
                    else:
                        lost += 1
                elif decision.outcome is Outcome.REPEAT:
                    # False means the record was resolved between the batch's
                    # state being read and this write. Counted apart: a repeat
                    # that wrote nothing is not a repeat, and reporting it as one
                    # would put a number in the false-alarm picture that nothing
                    # in the table supports.
                    written = repo.repeat(
                        conn,
                        machine_id=decision.machine_id,
                        rule_id=decision.rule_id,
                        now=now,
                    )
                    if written:
                        counts[Outcome.REPEAT] += 1
                    else:
                        lost += 1
                elif decision.outcome in (Outcome.RAISE, Outcome.FORECAST):
                    try:
                        detected = decision.outcome is Outcome.RAISE
                        issued = self._raise(conn, decision, open_findings, supersedes=detected)
                        target = raised if detected else predicted
                        target.append(issued)
                    except AlreadyLive:
                        # Another worker raised it between the state being read
                        # and this insert. That is suppression working across two
                        # processes; the batch carries on rather than ending.
                        lost += 1
                else:
                    counts[decision.outcome] += 1

        return Observation(
            raised=tuple(raised),
            forecast=tuple(predicted),
            repeated=counts[Outcome.REPEAT],
            suppressed=counts[Outcome.SUPPRESSED],
            in_cooldown=counts[Outcome.IN_COOLDOWN],
            quiet=quiet,
            lost_races=lost,
        )

    def _raise(
        self,
        conn: Connection[Any],
        decision: Decision,
        open_findings: dict[tuple[MachineId, Any], Any],
        *,
        supersedes: bool,
    ) -> Raised:
        finding = decision.finding
        assert finding is not None  # RAISE always carries one
        finding_ref = repo.raise_finding(conn, finding)

        # Keeping the in-memory copy honest: a second breach of the same rule
        # later in this batch is a repeat, not a second record. Without this the
        # unique index would refuse it - correctly - and the batch would end in
        # an exception rather than in a count.
        open_findings[(finding.machine_id, finding.rule_id)] = finding

        # ADR-023 section 7: what was predicted has happened. Two work orders for
        # one fault is the immediate reason; the other is that this is where a
        # prediction's error becomes measurable (ADR-020).
        #
        # **Only a detection supersedes.** A new forecast running this would mark
        # an older forecast on the same component as superseded - and hand the
        # accuracy loop a crossing that never happened, which is a measurement of
        # nothing dressed as a measurement of something.
        if not supersedes:
            return Raised(finding_ref=finding_ref, decision=decision, superseded=None)

        candidate = repo.open_prediction_for(
            conn, machine_id=finding.machine_id, component=finding.component
        )
        # Reported only if the UPDATE actually took it. A supersession that
        # matched no row and was reported anyway would hand ADR-020's accuracy
        # loop a measurement of something that never happened.
        superseded = (
            candidate
            if candidate is not None
            and candidate != finding_ref
            and repo.supersede(conn, predicted=candidate, by=finding_ref)
            else None
        )

        return Raised(finding_ref=finding_ref, decision=decision, superseded=superseded)

    def expire_stale_predictions(self, conn: Connection[Any]) -> list[FindingRef]:
        """Predictions whose ETA plus grace has passed with nothing happening.

        Expired rather than deleted (ADR-023 section 6): a prediction that did
        not come true is half of the accuracy measurement, and a table holding
        only the successful ones would describe a system that never gets it
        wrong.
        """
        return repo.expire_overdue_predictions(conn, now=self.clock.now(), grace=self.eta_grace)

    def rules_behind(
        self, conn: Connection[Any], refs: Collection[FindingRef]
    ) -> list[tuple[MachineId, RuleId]]:
        """Which (machine, rule) these Findings belong to, in any state.

        The trigger loop's half of `under_repair` (ADR-044 §6). The state is
        deliberately not filtered: the case ADR-023 §4 is about is a Finding
        resolved an hour ago whose repair is still under way.
        """
        return repo.rules_behind(conn, refs)

    def resolve(self, conn: Connection[Any], finding_ref: FindingRef) -> bool:
        """The condition is over, and the cooldown starts now."""
        return repo.resolve(conn, finding_ref, now=self.clock.now())

    def acknowledge(self, conn: Connection[Any], finding_ref: FindingRef) -> bool:
        return repo.acknowledge(conn, finding_ref)

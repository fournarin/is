"""The rule engine with a database behind it: signals in, Findings out.

State is loaded once per batch and the evaluation itself stays pure (ADR-042):
this module is the joining, and everything that decides anything is next door in
`domain.py` where it can be tested in a line.

It opens no connection. The caller supplies one, so a Finding and the work order
it produces commit together (ADR-017) - which is what stops a Finding existing
with nothing behind it, and a ticket referring to a Finding that was rolled back.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import timedelta
from typing import Any

from psycopg import Connection
from pydantic import BaseModel, ConfigDict

from pdm.contracts import FindingRef, MachineId, Severity, Signal
from pdm.platform.clock import Clock
from pdm.platform.config.schema import RuleConfig
from pdm.triggers import repo
from pdm.triggers.domain import Debounce, Decision, Outcome, evaluate


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
    repeated: int = 0
    suppressed: int = 0
    in_cooldown: int = 0
    quiet: int = 0

    @property
    def anything_happened(self) -> bool:
        return bool(self.raised) or bool(self.repeated)


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
    ) -> None:
        self.clock = clock
        self.rules = list(rules)
        # From policy.yaml, never from code: ADR-023's last consequence is that
        # these two live in configuration.
        self.cooldown = cooldown
        self.eta_grace = eta_grace
        self.debounce = Debounce()

    def observe(
        self,
        conn: Connection[Any],
        signals: Iterable[Signal],
        *,
        under_repair: Mapping[MachineId, Severity] | None = None,
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
        counts = {Outcome.REPEAT: 0, Outcome.SUPPRESSED: 0, Outcome.IN_COOLDOWN: 0}
        quiet = 0

        for signal in signals:
            decisions = evaluate(
                signal,
                self.rules,
                now=now,
                debounce=self.debounce,
                open_findings=open_findings,
                resolved_at=resolved_at,
                under_repair=under_repair or {},
                cooldown=self.cooldown,
            )
            for decision in decisions:
                if decision.outcome is Outcome.QUIET:
                    quiet += 1
                elif decision.outcome is Outcome.REPEAT:
                    repo.repeat(
                        conn,
                        machine_id=decision.machine_id,
                        rule_id=decision.rule_id,
                        now=now,
                    )
                    counts[Outcome.REPEAT] += 1
                elif decision.outcome is Outcome.RAISE:
                    raised.append(self._raise(conn, decision, open_findings))
                else:
                    counts[decision.outcome] += 1

        return Observation(
            raised=tuple(raised),
            repeated=counts[Outcome.REPEAT],
            suppressed=counts[Outcome.SUPPRESSED],
            in_cooldown=counts[Outcome.IN_COOLDOWN],
            quiet=quiet,
        )

    def _raise(
        self,
        conn: Connection[Any],
        decision: Decision,
        open_findings: dict[tuple[MachineId, Any], Any],
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
        superseded = repo.open_prediction_for(
            conn, machine_id=finding.machine_id, component=finding.component
        )
        if superseded is not None and superseded != finding_ref:
            repo.supersede(conn, predicted=superseded, by=finding_ref)

        return Raised(finding_ref=finding_ref, decision=decision, superseded=superseded)

    def expire_stale_predictions(self, conn: Connection[Any]) -> list[FindingRef]:
        """Predictions whose ETA plus grace has passed with nothing happening.

        Expired rather than deleted (ADR-023 section 6): a prediction that did
        not come true is half of the accuracy measurement, and a table holding
        only the successful ones would describe a system that never gets it
        wrong.
        """
        return repo.expire_overdue_predictions(conn, now=self.clock.now(), grace=self.eta_grace)

    def resolve(self, conn: Connection[Any], finding_ref: FindingRef) -> bool:
        """The condition is over, and the cooldown starts now."""
        return repo.resolve(conn, finding_ref, now=self.clock.now())

    def acknowledge(self, conn: Connection[Any], finding_ref: FindingRef) -> bool:
        return repo.acknowledge(conn, finding_ref)

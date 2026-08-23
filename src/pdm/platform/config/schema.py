"""Shapes of the three config files.

Config is a contract, not a bag of constants (design.md 9). It is versioned, it
is validated when the service boots, and a malformed file stops the boot rather
than being tolerated. The plant will want to change thresholds without a deploy,
several ADRs forbid hard-coding these values, and the simulator is only
reproducible if (config + seed) fully determines the outcome.

Every model forbids unknown keys. A misspelled setting that is silently ignored
is worse than one that fails: the operator sees a file that says 0.7 and a system
behaving as though it says 0.8.
"""

from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pdm.contracts import (
    ComponentLabel,
    LineId,
    MachineId,
    MachineModel,
    RuleId,
    Severity,
    ShiftId,
    SkillId,
    StationId,
    SymptomCode,
)

_STRICT = ConfigDict(frozen=True, extra="forbid")


# ── plant.yaml: the physical and organisational world ──────────────────────


class MachineConfig(BaseModel):
    model_config = _STRICT

    machine_id: MachineId
    model: MachineModel


class StationConfig(BaseModel):
    """One position on the line. See ADR-021 for why buffers are modelled."""

    model_config = _STRICT

    station_id: StationId
    seq: int = Field(ge=0)
    buffer_units: int = Field(default=0, ge=0)
    bottleneck_multiplier: float = Field(default=1.0, gt=0)
    machines: tuple[MachineConfig, ...] = ()


class LineConfig(BaseModel):
    model_config = _STRICT

    line_id: LineId
    takt_seconds: float = Field(gt=0)
    stations: tuple[StationConfig, ...]


class ShiftConfig(BaseModel):
    model_config = _STRICT

    shift_id: ShiftId
    starts_at: time
    ends_at: time


class PlantConfig(BaseModel):
    model_config = _STRICT

    version: int = Field(ge=1)
    # Where the plant is, as an IANA name. Shift boundaries are local wall-clock
    # times - "06:00" is when people arrive - and every moment they are compared
    # against is UTC (ADR-028). Read as UTC, a 06:00 shift in a plant at UTC+7
    # starts in the middle of the afternoon and the night shift's date rolls a
    # day early: wrong for one shift in three and right for the others, which is
    # the failure ADR-028 exists to prevent (ADR-045 §7).
    timezone: str
    lines: tuple[LineConfig, ...]
    # The single list both Playbook.required_skill and Technician.skills draw
    # from. Two vocabularies would fail to match in silence (ADR-027).
    skills: tuple[SkillId, ...]
    shifts: tuple[ShiftConfig, ...]

    @field_validator("timezone")
    @classmethod
    def _the_zone_exists_on_this_machine(cls, value: str) -> str:
        """Checked at boot, like every other name in this file.

        A zone that does not resolve is a container that starts, schedules a
        whole shift against the wrong roster, and reports nothing.
        """
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(
                f"{value!r} is not a timezone this machine knows: {error}. "
                f"Use an IANA name such as 'Asia/Bangkok' (ADR-045 §7)"
            ) from error
        return value


# ── rules.yaml: detection rules and the component labels they may use ───────


class RuleConfig(BaseModel):
    """One threshold rule.

    `component` is declared here, never inferred from the signal. A rule that
    cannot say which part it watches uses "unknown", and layer 2 then serves a
    diagnostic playbook rather than a repair one (ADR-009, ADR-016).
    """

    model_config = _STRICT

    rule_id: RuleId
    machine_model: MachineModel
    component: ComponentLabel
    symptom_code: SymptomCode

    metric_name: str
    comparison: str = Field(pattern="^(above|below)$")
    threshold: float
    # How long the condition must hold before it counts. Without it a single
    # noisy sample raises a Finding.
    for_seconds: int = Field(default=0, ge=0)
    severity: Severity

    # ADR-022 forbids any loop from proposing that a safety-linked threshold be
    # loosened, no matter how many false alarms it produces. That prohibition
    # needs a flag to act on, and the flag has to be set by the person writing
    # the rule rather than guessed later.
    safety_critical: bool = False


class RulesConfig(BaseModel):
    model_config = _STRICT

    version: int = Field(ge=1)
    # Component labels per machine model, in the same file as the rules that use
    # them, so the two cannot drift apart (ADR-016).
    components: dict[MachineModel, tuple[ComponentLabel, ...]]
    rules: tuple[RuleConfig, ...]


# ── policy.yaml: the tunable numbers ───────────────────────────────────────


class DispatchWeights(BaseModel):
    """w1 to w5 of the 3C score.

    These have no external source. They are starting values to be derived from
    the simulator and Loop 6, not measurements, and they are the one group in
    this file that must not be quoted in the report as if they were tuned.
    """

    model_config = _STRICT

    severity: float = Field(ge=0)
    downtime: float = Field(ge=0)
    skill_match: float = Field(ge=0)
    waiting: float = Field(ge=0)
    eta_urgency: float = Field(ge=0)


class LoadThresholds(BaseModel):
    """The two boundaries of the load gate (ADR-011)."""

    model_config = _STRICT

    light_below: float = Field(gt=0, lt=1)
    heavy_at_or_above: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _light_is_below_heavy(self) -> LoadThresholds:
        if self.light_below >= self.heavy_at_or_above:
            raise ValueError(
                f"the light threshold must sit below the heavy one, "
                f"got light={self.light_below} heavy={self.heavy_at_or_above}"
            )
        return self


class TrendConfig(BaseModel):
    """Parameters of the trend extrapolation that produces predictions (ADR-020)."""

    model_config = _STRICT

    window_minutes: int = Field(gt=0)
    min_samples: int = Field(ge=2)
    # Beyond this horizon the extrapolation is not reported. ADR-020 requires
    # error to be reported per horizon precisely because it grows with distance.
    max_horizon_hours: int = Field(gt=0)


class TriggerPolicy(BaseModel):
    model_config = _STRICT

    # After a Finding resolves, how long before the same rule may raise another.
    # Without it a sensor oscillating across the threshold produces an endless
    # stream of them (ADR-023).
    cooldown_minutes: int = Field(ge=0)
    # How long past a predicted ETA to wait before marking it expired.
    eta_grace_minutes: int = Field(ge=0)
    trend: TrendConfig


class RetrievalProfile(BaseModel):
    model_config = _STRICT

    min_score: float = Field(ge=0, le=1)
    candidates: int = Field(gt=0)
    abstain: bool
    # Safety questions use a stricter bar. Only meaningful on the runtime
    # profile, where nobody stands between the system and the technician.
    safety_min_score: float | None = Field(default=None, ge=0, le=1)


class RetrievalPolicy(BaseModel):
    """Two profiles, because the cost of the two kinds of mistake is not the
    same at authoring time and at runtime (ADR-015)."""

    model_config = _STRICT

    authoring: RetrievalProfile
    runtime: RetrievalProfile

    @model_validator(mode="after")
    def _authoring_is_the_looser_profile(self) -> RetrievalPolicy:
        """ADR-015: recall leads at authoring, precision leads at runtime.

        If these were ever swapped, the profile with nobody checking its output
        would be the permissive one, which is the single arrangement ADR-003
        exists to prevent.
        """
        if self.authoring.min_score >= self.runtime.min_score:
            raise ValueError(
                f"the authoring profile must be the looser one (ADR-015), got "
                f"authoring={self.authoring.min_score} runtime={self.runtime.min_score}"
            )
        if self.runtime.abstain is False:
            raise ValueError("the runtime profile must abstain when evidence is thin (ADR-015)")
        return self


class JobTiming(BaseModel):
    """Heartbeat and death thresholds for one job class (ADR-026)."""

    model_config = _STRICT

    heartbeat_seconds: int = Field(gt=0)
    dead_after_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def _death_comes_after_several_missed_beats(self) -> JobTiming:
        """A job must be allowed to miss a beat without being declared dead.

        With the two set equal, one slow network round trip reaps a healthy
        worker, its job is handed to another, and the first one carries on - two
        workers on the same job, which is precisely what SKIP LOCKED was chosen
        to prevent.
        """
        if self.dead_after_seconds < self.heartbeat_seconds * 3:
            raise ValueError(
                f"dead_after_seconds must allow at least three missed beats, got "
                f"{self.dead_after_seconds}s against a {self.heartbeat_seconds}s beat"
            )
        return self


class JobPolicy(BaseModel):
    model_config = _STRICT

    runtime: JobTiming
    authoring: JobTiming


class DispatchPolicy(BaseModel):
    """How often a scheduling round runs (ADR-011, design.md 6.2).

    A cadence rather than a trigger: the queue changes for reasons no event
    reaches - a shift starts, a technician's remaining minutes fall, a predicted
    crossing gets closer - so a round that only ran when something arrived would
    leave a shift ranked by facts that stopped being true.
    """

    model_config = _STRICT

    round_seconds: int = Field(gt=0)
    # How long CP-SAT may search before the round takes the answer it has
    # (ADR-054). A bound rather than a target: the solver returns the best
    # feasible schedule it found, and a round that has not found one falls back
    # to the ranked queue rather than returning nothing.
    solver_seconds: float = Field(gt=0)


class EstimatePolicy(BaseModel):
    """The two numbers Loop 1 needs before it may say anything (ADR-066).

    Both are recorded decisions rather than measurements, and the reasoning is in
    ADR-066. The validator below is the part that matters: ADR-022 bounds how far
    one cycle may move an estimate, and a bound that lives only in a document is
    one a later edit to this file can raise without anybody noticing.
    """

    model_config = _STRICT

    # How many usable closed jobs before the loop proposes at all.
    min_observations: int = Field(ge=2)
    # How far one proposal may move the estimate, as a fraction of it.
    max_change_ratio: float = Field(gt=0)

    @model_validator(mode="after")
    def _one_cycle_may_not_move_further_than_adr_022_allows(self) -> EstimatePolicy:
        if self.max_change_ratio > 0.20:
            raise ValueError(
                f"ADR-022 bounds the duration loop at plus or minus twenty percent per cycle, "
                f"got {self.max_change_ratio}. Raising it is a new record, not a config edit"
            )
        return self


class PolicyConfig(BaseModel):
    model_config = _STRICT

    version: int = Field(ge=1)
    weights: DispatchWeights
    load: LoadThresholds
    triggers: TriggerPolicy
    dispatch: DispatchPolicy
    estimates: EstimatePolicy
    retrieval: RetrievalPolicy
    # Rough estimates used when no playbook exists, so long-tail work still gets
    # a duration and stays in the queue instead of vanishing (design.md 3.2).
    fallback_minutes: dict[MachineModel, dict[Severity, int]]
    jobs: JobPolicy

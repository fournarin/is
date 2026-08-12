"""The backend that talks to `llm-server` (ADR-029, ADR-037 section 9).

Reachable from `worker-authoring` and from nothing else, which is enforced by
the compose network split rather than by this file (invariant 15). The import
rule that keeps `pdm.llm` out of runtime modules is the other half.

The transport is `urllib` from the standard library. ADR-008 forbids a
dependency without a record, and one HTTP POST with a JSON body does not earn
one - `httpx` is present only because Starlette's test client pulls it in, which
is not the same as it being a dependency of the system.

Nothing here trusts the reply. Whatever comes back is turned into a `Proposal`
and checked by `authoring/drafting.py` like any other backend's.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable

from pdm.llm.domain import DraftRequest, Proposal, ProposalKind, ProposedStep
from pdm.llm.prompt import SYSTEM, build

# The default in docker-compose.yml. Named by service, on the network `api` is
# not a member of: from the API container this name does not resolve, which is
# ADR-003 enforced by the absence of a route rather than by a rule.
DEFAULT_BASE_URL = "http://llm-server:11434"

# Seconds. Drafting is an authoring job with a fifteen-minute dead threshold
# (policy.yaml), and a request that hangs past this leaves the job to the reaper
# rather than holding a worker for the whole window.
DEFAULT_TIMEOUT = 120.0

Transport = Callable[[str, bytes, float], bytes]


class ModelServerError(Exception):
    """The model server could not be reached, or answered with nonsense.

    One exception for both because the caller does the same thing either way:
    fail the job and leave it to be retried. What differs is what goes in the
    message, and that is what somebody reads at three in the morning.
    """


def _post(url: str, body: bytes, timeout: float) -> bytes:
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return bytes(response.read())
    except (urllib.error.URLError, TimeoutError) as error:
        raise ModelServerError(f"{url}: {error}") from error


def _minutes(value: object) -> int | None:
    """A duration the scheduler can compute with, or nothing.

    Whole minutes above zero and nothing else. `0.5` truncated to zero and was
    then rejected by the contract as a pydantic error escaping this module; `true`
    is an `int` in Python and would have become a one-minute estimate that reads
    like a figure off a manual. Neither is a duration, and a duration this module
    is unsure about is one the reviewer should be asked for (ADR-037 §8).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    return None


class LlmServerDrafter:
    """Implements `Drafter` by asking a model. Tier 3 only.

    Never a fallback for the extractive backend and never fallen back to:
    a system that quietly swapped one for the other would report drafts of two
    different qualities under one name (ADR-037 section 9).
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Transport = _post,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._transport = transport

    def propose(self, request: DraftRequest) -> Proposal:
        if not request.evidence:
            return Proposal(kind=ProposalKind.NOTHING)

        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": build(request)},
                ],
                "stream": False,
                # JSON mode, greedy decoding, fixed seed. None of the three makes
                # the model reproducible across versions - which is why the
                # published figures come from the extractive backend - but they
                # remove the variation that is ours to remove.
                "format": "json",
                "options": {"temperature": 0.0, "seed": 0},
            }
        ).encode()

        raw = self._transport(f"{self.base_url}/api/chat", body, self.timeout)
        return self._parse(raw, request)

    def _parse(self, raw: bytes, request: DraftRequest) -> Proposal:
        try:
            envelope = json.loads(raw)
            answer = json.loads(envelope["message"]["content"])
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise ModelServerError(
                f"the model did not return the JSON it was asked for: {error}"
            ) from error

        if not isinstance(answer, dict):
            # A JSON array or a bare string is valid JSON and not an answer. Left
            # unchecked this reaches `.get` and leaves the module as an
            # AttributeError, which the worker cannot tell from a bug in here.
            raise ModelServerError(f"the model returned {type(answer).__name__}, not an object")

        kind = answer.get("kind")
        if kind not in {item.value for item in ProposalKind}:
            raise ModelServerError(f"the model answered with kind={kind!r}")

        steps = []
        for step in answer.get("steps") or []:
            if not isinstance(step, dict):
                # A step written as a bare string has no citation, and a step
                # with no citation is one nobody can check after an accident
                # (principle 2).
                continue
            label = step.get("evidence")
            text = str(step.get("text") or "").strip()
            if not text:
                continue
            if (
                not isinstance(label, int)
                or isinstance(label, bool)
                or not 1 <= label <= len(request.evidence)
            ):
                # A label pointing at nothing cannot be resolved to a page, and a
                # step with no page is a step nobody can check after an accident
                # (principle 2). Dropped here rather than passed on with a guessed
                # citation, and the gate would reject it in any case.
                continue
            steps.append(ProposedStep(text=text, cites=request.evidence[label - 1].ref))

        skill = answer.get("required_skill")
        return Proposal(
            kind=ProposalKind(kind),
            steps=tuple(steps),
            # Strings only. `str()` on whatever arrived would put
            # "{'name': 'torque wrench'}" on a tool list a technician reads, and
            # tools are not gated the way steps are.
            tools=tuple(
                tool.strip()
                for tool in (answer.get("tools") or [])
                if isinstance(tool, str) and tool.strip()
            ),
            required_skill=str(skill).strip() if isinstance(skill, str) and skill.strip() else None,
            estimated_minutes=_minutes(answer.get("estimated_minutes")),
        )

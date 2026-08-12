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

        kind = answer.get("kind")
        if kind not in {item.value for item in ProposalKind}:
            raise ModelServerError(f"the model answered with kind={kind!r}")

        steps = []
        for step in answer.get("steps") or []:
            label = step.get("evidence")
            text = (step.get("text") or "").strip()
            if not text:
                continue
            if not isinstance(label, int) or not 1 <= label <= len(request.evidence):
                # A label pointing at nothing cannot be resolved to a page, and a
                # step with no page is a step nobody can check after an accident
                # (principle 2). Dropped here rather than passed on with a guessed
                # citation, and the gate would reject it in any case.
                continue
            steps.append(ProposedStep(text=text, cites=request.evidence[label - 1].ref))

        minutes = answer.get("estimated_minutes")
        skill = answer.get("required_skill")
        return Proposal(
            kind=ProposalKind(kind),
            steps=tuple(steps),
            tools=tuple(str(tool) for tool in (answer.get("tools") or []) if str(tool).strip()),
            required_skill=str(skill) if skill else None,
            estimated_minutes=int(minutes)
            if isinstance(minutes, int | float) and minutes
            else None,
        )

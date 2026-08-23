"""The destination that is somebody else's system (ADR-070, ADR-074).

The third sink and the first one reached over a network, which is what makes it
worth building before anybody has access to the plant's CMMS: it is the first
destination that can hang, answer 500, or accept a ticket and lose it. Until
now ADR-068's refusal path has been exercised only by a double that was asked
to fail.

**The contract is ours and is written down in ADR-074 §1**, not guessed from a
product. An adapter written against an imagined SAP PM or Maximo interface
would look finished, pass its tests, and be undiscoverably wrong until the day
access is granted - which is worse than no adapter, because it consumes the
slice that would have built the real one (ADR-070 §2).

`urllib` rather than a client library: ADR-008 forbids a dependency without a
record, and one POST does not need one.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from pdm.sinks.domain import DeliveryFailed, Receipt, Ticket

# The schemes this sink will speak. `urllib` opens `file:///var/tmp/x` as
# readily as an address, so a base URL that arrived from the environment with
# the wrong scheme would give a sink that reports every delivery as successful
# while writing to a local path (ADR-074 §5). Checked by the registry, at
# composition, where `TICKET_DIR`'s absence is checked.
SCHEMES = ("http", "https")

# The one path this contract has. A CMMS with a different one is configured
# through `CMMS_BASE_URL`, which may carry a prefix.
PATH = "/work-orders"


class CmmsSink:
    """One POST per ticket, and the identifier the destination issues back.

    Holds no connection: `urllib` opens one per request. A pooled client would
    be worth having against a destination this process talked to constantly,
    and this one is called at most fifty times per five-minute round
    (ADR-068 §4).
    """

    # Five seconds, derived rather than chosen (ADR-074 §2): ADR-068 §4 caps a
    # delivery pass at fifty tickets and `dispatch.round_seconds` is 300, so
    # 50 x 5 = 250 keeps the worst case - a destination that accepts every
    # connection and answers none - inside the round that started it. Asserted
    # in `tests/sinks/test_the_third_destination.py`, because both numbers it
    # comes from can be changed by somebody who never reads that record.
    TIMEOUT_SECONDS: float = 5.0

    def __init__(
        self, base_url: str, *, token: str, timeout_seconds: float = TIMEOUT_SECONDS
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    @property
    def destination(self) -> str:
        return "cmms"

    @property
    def url(self) -> str:
        return f"{self.base_url}{PATH}"

    def deliver(self, ticket: Ticket) -> Receipt:
        """Hand the ticket over, or say what the destination did instead.

        Every failure below is a `DeliveryFailed` and therefore recorded and
        retried (ADR-074 §3). None of them says anything about this system's own
        correctness - they say the destination is down, misconfigured, or not
        what we think it is - and a round rolled back because a CMMS was
        restarting would take a scheduling decision away from a technician who
        can already see the job on their own screen (ADR-068 §2).
        """
        answer = self._post(self._body(ticket), idempotency_key=str(ticket.work_order_ref))
        return Receipt(external_ref=self._identifier(answer))

    def _body(self, ticket: Ticket) -> bytes:
        """The ticket under one key, as UTF-8 (ADR-074 §1).

        Wrapped rather than bare so that a field can be added later without
        every existing one moving in somebody else's system. Unescaped because
        `reason` and the steps are Thai, and a body that arrived as `\\u0e23`
        is one nobody can check by eye against the technician's screen.
        """
        document = {"ticket": ticket.model_dump(mode="json")}
        return json.dumps(document, ensure_ascii=False).encode("utf-8")

    def _post(self, body: bytes, *, idempotency_key: str) -> dict[str, Any]:
        # The scheme is checked at composition rather than here (ADR-074 §5), so
        # that a base URL that is not a network address fails before the first
        # round rather than on the first ticket.
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self.token}",
                # The same key as `work_order_ref` in the body, on purpose: the
                # header is what a destination deduplicating at its edge reads,
                # the body is what one deduplicating in its application reads,
                # and at-least-once means both are eventually asked the same
                # question twice (ADR-074 §1).
                "Idempotency-Key": idempotency_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            # Read the body before it closes: a CMMS that explains its refusal
            # is the difference between "502" and something somebody can act on.
            raise DeliveryFailed(
                f"{self.url} answered {error.code}: {_excerpt(_read(error))}"
            ) from error
        except OSError as error:
            # `URLError` and `TimeoutError` are both `OSError`: connection refused,
            # a name that does not resolve, or a destination that accepted the
            # connection and then said nothing within the timeout.
            reason = getattr(error, "reason", error)
            raise DeliveryFailed(f"{self.url} could not be reached: {reason}") from error

        try:
            answer = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DeliveryFailed(
                f"{self.url} accepted the ticket and answered with something that is not "
                f"JSON: {_excerpt(raw)}"
            ) from error
        if not isinstance(answer, dict):
            raise DeliveryFailed(
                f"{self.url} accepted the ticket and answered with JSON that is not an "
                f"object: {_excerpt(raw)}"
            )
        return answer

    def _identifier(self, answer: dict[str, Any]) -> str:
        """The destination's own number, or a refusal saying it named none.

        A 2xx with nothing in `id` is the case ADR-070 §2 says a CMMS adds and
        neither of the other two destinations can produce. It is treated as the
        ticket not having been taken (ADR-074 §4): recording our own ref the way
        `OwnSystemSink` does would leave a row saying `delivered` that cannot
        reconcile the two systems, which is the only thing `external_ref` is for.

        The cost is a duplicate at the destination next round, and that is the
        failure this project already chose over a missing one (ADR-068 §1).
        """
        issued = answer.get("id")
        if not isinstance(issued, str) or not issued.strip():
            raise DeliveryFailed(
                f"{self.url} accepted the ticket and returned no identifier, so there is "
                "nothing to reconcile it by; sending it again next round"
            )
        return issued.strip()


def _read(error: urllib.error.HTTPError) -> bytes:
    """Whatever the refusal said, or nothing. Never a second failure."""
    try:
        return bytes(error.read())
    except OSError:
        return b""


def _excerpt(raw: bytes, *, limit: int = 200) -> str:
    """Enough of the destination's answer to act on, in a message stored on a row.

    Capped because `last_error` is read by a person and the body of a refusal
    can be an entire HTML error page.
    """
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return "(no body)"
    return text if len(text) <= limit else f"{text[:limit]}..."


def is_a_network_address(base_url: str) -> bool:
    """Whether this is a destination at all, checked before the first round.

    See `SCHEMES`. Lives here rather than in the registry so that the rule and
    the reason for it sit beside the code the rule protects.
    """
    parsed = urlsplit(base_url)
    return parsed.scheme in SCHEMES and bool(parsed.netloc)

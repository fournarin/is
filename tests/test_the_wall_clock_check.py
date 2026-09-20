"""The gate behind invariant 14, tested against each way of reading the clock.

A gate with no test of its own reports success whether or not it is looking at
anything, and this one was narrower than the rule it is named after: it matched
five call patterns as text, so `datetime.today()`, `time.time_ns()`,
`time.monotonic_ns()` and every aliased import passed it (#105). None of those
were in `src/` when that was found, which is exactly why it went unnoticed - the
check was green for the code that existed and would have been green for the code
that broke it.

One test per form, because the forms are the specification (#108). The aliased
cases are the ones a regular expression cannot reach at all.
"""

from __future__ import annotations

import pytest

from scripts import check_no_wall_clock as gate

READS_THE_CLOCK = [
    "import time\nx = time.time()\n",
    "import time\nx = time.time_ns()\n",
    "import time\nx = time.monotonic()\n",
    "import time\nx = time.monotonic_ns()\n",
    "import time\nx = time.perf_counter()\n",
    "import time\nx = time.perf_counter_ns()\n",
    "import time\nx = time.localtime()\n",
    "from datetime import datetime\nx = datetime.now()\n",
    "from datetime import datetime\nx = datetime.utcnow()\n",
    "from datetime import datetime\nx = datetime.today()\n",
    "from datetime import date\nx = date.today()\n",
    "import datetime\nx = datetime.datetime.now()\n",
    "import datetime\nx = datetime.date.today()\n",
]

ALIASED = [
    "from datetime import datetime as dt\nx = dt.now()\n",
    "from datetime import datetime as dt\nx = dt.today()\n",
    "import datetime as d\nx = d.datetime.now()\n",
    "import time as t\nx = t.monotonic()\n",
    "from time import monotonic as elapsed\nx = elapsed()\n",
    "from time import time_ns\nx = time_ns()\n",
]

DOES_NOT = [
    # Arithmetic on a datetime somebody was handed is not a clock read.
    "from datetime import timedelta\nx = when + timedelta(hours=1)\n",
    # The Clock port is how the rest of the system asks, and asking is allowed.
    "def f(clock):\n    return clock.now()\n",
    # A method that happens to share a name with one on datetime.
    "def f(stack):\n    return stack.today()\n",
    # Naming the banned function without calling it - a type annotation, say.
    "import time\nf = time.monotonic\n",
]


class TestEveryFormOfAskingTheOperatingSystem:
    @pytest.mark.parametrize("source", READS_THE_CLOCK)
    def test_a_direct_call_is_caught(self, source: str) -> None:
        assert gate.wall_clock_calls(source), source

    @pytest.mark.parametrize("source", ALIASED)
    def test_an_aliased_import_is_caught(self, source: str) -> None:
        """The whole reason for reading the syntax tree. `dt.now()` shares no
        characters with any pattern the old gate matched."""
        assert gate.wall_clock_calls(source), source

    def test_the_line_it_names_is_the_line_of_the_call(self) -> None:
        found = gate.wall_clock_calls("import time\n\n\nx = time.monotonic()\n")

        assert found == ["4: x = time.monotonic()"]

    def test_a_call_inside_a_nested_function_is_still_found(self) -> None:
        source = "import time\n\n\ndef outer():\n    def inner():\n        return time.time()\n"

        assert gate.wall_clock_calls(source)


class TestWhatItMustNotRefuse:
    @pytest.mark.parametrize("source", DOES_NOT)
    def test_ordinary_code_passes(self, source: str) -> None:
        assert gate.wall_clock_calls(source) == [], source


class TestTheEscapeHatch:
    def test_a_marked_line_is_allowed(self) -> None:
        source = "from datetime import datetime\nx = datetime.now(UTC)  # allow: wall-clock\n"

        assert gate.wall_clock_calls(source) == []

    def test_the_marker_may_sit_on_any_line_of_a_call_spread_over_several(self) -> None:
        """SimulatedClock's own call is written over three lines. A hatch that
        only looked at the first would send somebody to reformat their code to
        satisfy a checker."""
        source = (
            "from datetime import datetime\nx = datetime.now(\n    UTC,  # allow: wall-clock\n)\n"
        )

        assert gate.wall_clock_calls(source) == []

    def test_the_marker_does_not_excuse_the_next_call(self) -> None:
        source = "import time\nx = time.monotonic()  # allow: wall-clock\ny = time.monotonic()\n"

        assert gate.wall_clock_calls(source) == ["3: y = time.monotonic()"]


class TestAFileItCannotRead:
    def test_a_module_that_will_not_parse_is_reported_rather_than_skipped(self) -> None:
        """Silence on an unreadable file is the same defect as a pattern that
        misses a form: the gate passes, and not because the code is clean."""
        found = gate.wall_clock_calls("def broken(:\n", filename="broken.py")

        assert found and "cannot be parsed" in found[0]


class TestTheRepositoryItself:
    def test_the_source_tree_passes(self) -> None:
        assert gate.main() == 0

    def test_the_clock_port_would_not_pass_if_it_were_checked(self) -> None:
        """The exemption is doing work. If `platform/clock.py` ever stops
        holding calls this gate would refuse, the port has moved and the
        exemption is stale."""
        source = (gate.SOURCE_ROOT / "platform" / "clock.py").read_text(encoding="utf-8")

        assert gate.wall_clock_calls(source)

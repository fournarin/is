"""The rehearsal: the whole stack from nothing, then the screen checks (ADR-067).

    uv run python scripts/rehearse.py            # reuse whatever is already up
    uv run python scripts/rehearse.py --fresh    # destroy the volumes first, then start cold
    uv run python scripts/rehearse.py --down     # stop the stack when the checks finish

`web/check-sign-in.py` and its three siblings are the only tests in this
repository that drive the screens the way a technician's phone does, and no CI
tier can run them: each needs a database, a built web app and a running API at
the same time. That is why one of them had drifted out of date without anything
noticing (#70). This script is what runs them.

It is also the thing to run before promising anybody a demo. ADR-007 asks for a
demo the advisor can negotiate with and ADR-014 reserves the technician trial
unconditionally; neither can be booked until somebody can be sure the stack still
starts. `docs/demo.md` is the page to read afterwards - what to click, in what
order, as whom.

It needs room - something like ten gigabytes for the images, the build cache and
the volumes together. A Docker daemon that meets a full disk mid-pull stops
answering and has to be restarted, so `docker system df` first is cheaper than it
looks.

Nothing here is a substitute for CI. Every gate in `.github/workflows/ci.yml`
still runs on every push; this covers the one seam those gates cannot reach.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# `.env.example` rather than `.env`, and this is deliberate. A cold clone has no
# `.env` - copying the example is the first thing its own header tells you to do
# - so rehearsing against the example is rehearsing what a newcomer actually has.
# A key that is missing from it then fails here rather than on their machine.
#
# `--progress` is chosen from whether anybody is watching. Compose redraws its
# progress in a terminal and reprints it line by line when it is not in one, and
# a redirected first run - every layer of three images, a line at a time - wrote
# a log large enough to fill the disk and take the Docker daemon down with it.
COMPOSE = [
    "docker",
    "compose",
    "--progress",
    "tty" if sys.stdout.isatty() else "quiet",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.rehearsal.yml",
    "--env-file",
    ".env.example",
]

# The ports docker-compose.yml publishes. Polled from the host rather than from
# inside the network on purpose: these are the two addresses a person types, so
# a stack that answers only on its internal names has not finished starting.
API_HEALTH = "http://localhost:8000/health"
WEB_SIGN_IN = "http://localhost:3000/sign-in"

# Three minutes. The API loads the embedding and reranker models in-process at
# boot (ADR-029), and the web container serves nothing until Next has finished
# starting; on a cold machine both together have taken over a minute. This is a
# timeout, not a measurement - it decides how long to wait before reporting a
# failure, and nothing in the system reads it.
START_TIMEOUT_SECONDS = 180

SEED = ["python", "scripts/seed_demo.py"]

# Run after the checks, never before: every check after the first truncates
# `account` and `technician` on its way through, so a roster seeded earlier is a
# roster the next check deletes (ADR-078).
ROSTER = ["python", "scripts/seed_demo_roster.py"]

# The other claim. The checks prove the screens answer; this proves there is
# something on them (`scripts/demo_ready.py`).
READY = ["python", "scripts/demo_ready.py"]

# How long to wait for the first round after worker-runtime comes back. A round
# runs every `dispatch.round_seconds` - 300 in the shipped policy - and the wait
# is a little over two of them, so a single missed tick does not read as a
# broken stack. Polled rather than slept: on a warm run the answer is usually
# immediate, because a round has already run.
READY_TIMEOUT_SECONDS = 660
READY_POLL_SECONDS = 15

# Order matters, and it is not the order the files were written in.
#
# `check-sign-in.py` signs in as the accounts `seed_demo.py` creates, so it has
# to run while they exist. The other three each TRUNCATE `account` and seed a
# world of their own, which destroys those accounts - so they run after it, and
# the demo world is seeded again at the end.
CHECKS = (
    "web/check-sign-in.py",
    "web/check-the-technicians-screen.py",
    "web/check-the-review-screen.py",
    "web/check-the-overview-screen.py",
    "web/check-reporting-a-fault.py",
)


@dataclass(frozen=True)
class Result:
    """What one check did. The output is kept even when it passed.

    A check that passes while printing a warning is the case this script exists
    to catch, and a summary of ticks alone would hide it.
    """

    name: str
    ok: bool
    output: str


def say(message: str) -> None:
    print(f"\n\033[1m{message}\033[0m", flush=True)


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """One compose command, its output going straight to the terminal.

    Not captured: a build that is slow is a build somebody should be able to
    watch, and a pull that is waiting on the network looks identical to a hang
    when its output is swallowed.
    """
    return subprocess.run([*COMPOSE, *args], cwd=REPO, text=True, check=check)


def wait_until_ready() -> Result:
    """Poll `demo_ready.py` until the chain reaches the shift lead, or give up.

    The checks that ran above each seeded their own world and truncated it
    again, so passing them says the screens answer - not that anything is on
    them. What a person opening this stack sees is decided by a round that has
    not run yet at this point, and the wait is the difference between handing
    somebody a demo and handing them an empty queue.

    Failure here is a real failure and not a slow one: `demo_ready.py` names the
    link that is missing, and every one of its answers is something a person has
    to fix before showing this to anybody.
    """
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    attempt = in_the_stack(READY)
    while not attempt.ok and time.monotonic() < deadline:
        remaining = int(deadline - time.monotonic())
        print(f"  not yet; {remaining}s left before this is a failure", flush=True)
        time.sleep(READY_POLL_SECONDS)
        attempt = in_the_stack(READY)
    return Result(name="the demo has something to show", ok=attempt.ok, output=attempt.output)


def in_the_stack(command: list[str]) -> Result:
    """Run one command in the rehearsal container, on the app network.

    Captured, because the caller decides what to do with a failure: one check
    failing must not stop the other three, and the whole list is the useful
    output (`--exit-code-from` would not give us that).
    """
    done = subprocess.run(
        [*COMPOSE, "run", "--rm", "--no-deps", "rehearsal", *command],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    return Result(
        name=command[-1],
        ok=done.returncode == 0,
        output=(done.stdout + done.stderr).strip(),
    )


def answering(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return 200 <= int(response.status) < 400
    except urllib.error.HTTPError as error:
        # A sign-in page that redirects, or an endpoint that asks for a session,
        # is a web server that has started. Only a connection that cannot be made
        # means it has not.
        return int(error.code) < 500
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def wait_for(url: str, what: str) -> bool:
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if answering(url):
            print(f"  ok   {what} answers on {url}")
            return True
        time.sleep(2)
    print(f"  FAIL {what} did not answer on {url} within {START_TIMEOUT_SECONDS}s")
    print(f"       `{' '.join(COMPOSE)} logs` is where the reason will be")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="destroy the stack's volumes first, so the run really does start from nothing",
    )
    parser.add_argument(
        "--down",
        action="store_true",
        help="stop the stack when the checks are done, instead of leaving it up for a demo",
    )
    args = parser.parse_args()

    if args.fresh:
        # Named volumes only, and only this project's. `down -v` does not touch
        # a developer's own PostgreSQL, and it is behind a flag because the
        # document store is one of the two things ADR-019 says to back up.
        say("Destroying this stack's volumes, so the start below is a cold one")
        compose("down", "-v", "--remove-orphans", check=False)

    # `--scale worker-runtime=0`, and it is the least obvious line in this file.
    # That container runs a dispatch round every `round_seconds` even with no
    # signal source at all - scheduled and reported work needs no sensor
    # (ADR-010) - so leaving it running would place work orders in the middle of
    # a check that is asserting on the ones it seeded itself. It is started at
    # the end, after the checks, because a demo wants it and the checks do not.
    say("Starting the stack (the first run builds two images and pulls three)")
    if not sys.stdout.isatty():
        print("  no terminal here, so Compose is quiet; this is the slow step", flush=True)
    compose("up", "-d", "--build", "--scale", "worker-runtime=0")

    say("Waiting for the two addresses a person types")
    up = wait_for(API_HEALTH, "the API") and wait_for(WEB_SIGN_IN, "the web app")
    if not up:
        return 1

    say("Seeding the demo world: accounts, roles and the synthetic manuals")
    seeded = in_the_stack(SEED)
    print(seeded.output)
    if not seeded.ok:
        print("\nThe seed failed, so the checks below would only report its absence.")
        return 1

    say(f"The {len(CHECKS)} checks, in the order the seeding allows")
    results: list[Result] = []
    for check in CHECKS:
        print(f"\n--- {check}")
        result = in_the_stack(["python", check])
        print(result.output or "  (no output)")
        results.append(result)

    # Every screen check after the first truncated `account` on its way through.
    # Without this, a rehearsal that reported nothing but passes would leave
    # behind a stack nobody can sign in to - the opposite of what it is for.
    say("Seeding the demo world again, over what the checks truncated")
    reseeded = in_the_stack(SEED)
    if not reseeded.ok:
        print(reseeded.output)
        results.append(Result(name="the demo world survives the checks", ok=False, output=""))

    # The roster the checks do not leave behind, and `seed_demo.py` will not
    # write: three technicians who do not exist, so that the round has somebody
    # to place work on and the demo can show layers 3 and 4 at all (ADR-078).
    say("Seeding the demo roster: three technicians who do not exist")
    rostered = in_the_stack(ROSTER)
    print(rostered.output or "  (no output)")
    if not rostered.ok:
        results.append(Result(name="the demo has a roster", ok=False, output=""))

    if args.down:
        say("Stopping the stack")
        compose("down", check=False)
    else:
        say("Starting worker-runtime, which the checks needed stopped")
        compose("up", "-d", "--no-deps", "worker-runtime", check=False)

        say("Waiting for the first round to place work, so the demo has something on it")
        ready = wait_until_ready()
        print(ready.output or "  (no output)")
        results.append(ready)

    say("What the rehearsal found")
    # Said before the results rather than after. A warm run reuses a database
    # somebody may have hand-fixed, and reading its ticks as proof that the
    # stack starts from nothing is the one wrong conclusion available here.
    print(
        "  started from nothing (--fresh)"
        if args.fresh
        else "  reused the volumes that were already there; --fresh starts cold"
    )
    for result in results:
        print(("  ok   " if result.ok else "  FAIL ") + result.name)
    failed = [result for result in results if not result.ok]
    if failed:
        print(f"\n{len(failed)} of {len(results)} failed. The output of each is above.")
        return 1

    # "checks" rather than "screens": the last entry in `results` is the wait for
    # a round to place work, which is not a screen and is the point of the run.
    print(f"\nAll {len(results)} checks passed. `docs/demo.md` says what to click and as whom.")
    if not args.down:
        print("The stack is still up; SIGNAL_SOURCE is synthetic, so work orders will")
        print("appear on their own. Every one of them is about a machine that is not")
        print("there (ADR-044). Stop it with:")
        print(f"  {' '.join(COMPOSE)} down")
    return 0


if __name__ == "__main__":
    sys.exit(main())

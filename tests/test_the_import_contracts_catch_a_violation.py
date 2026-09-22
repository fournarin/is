"""Invariants 1 and 10, broken on purpose against the contracts that hold them.

`lint-imports` passing on `src/pdm` says that today's tree contains no violation.
It does not say that the contract would catch one, and those are different
claims: a contract whose `source_modules` list has been emptied by a rename, or
whose `forbidden_modules` no longer name the package they were written about,
passes exactly as loudly as one that works. Invariant 1 is the rule ADR-003
calls the highest-leverage in the system, and invariant 10 is the precondition
for measuring anything at all - neither should rest on a gate nobody has seen
refuse.

So each test here builds a package tree that violates the rule and requires
`lint-imports` to exit 1 against it.

**The contracts under test are the real ones.** The configuration is read from
`.importlinter`, and the only thing changed is the root package name, from `pdm`
to `probe`, so that a tree can be stood up in `tmp_path` without shadowing the
installed package. Names outside the root package - `psycopg`, `urllib` - are
left alone, because a rewritten `psycopg` would test a rule this repository does
not have. If somebody deletes a contract or renames the modules it names,
`_mirror` raises rather than quietly testing nothing: that is the failure mode
these tests exist for.

Each case runs `lint-imports` in a subprocess. In-process would be faster and
wrong: every tree here is called `probe`, and the second one imported in a
process would be served from `sys.modules` as the first.
"""

from __future__ import annotations

import configparser
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
REAL_CONFIG = REPO / ".importlinter"

# The name the mirrored tree takes. Anything but `pdm`: a tree named `pdm` in
# tmp_path would be built against, or shadowed by, the installed package
# depending on which directory came first on the path, and the test would be
# measuring sys.path rather than the contract.
PROBE = "probe"

LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"

STUB = '"""A module that exists so a contract has something to name."""\n'


@dataclass(frozen=True)
class Mirror:
    """A contract from `.importlinter`, over a tree that can be broken."""

    contract: str
    root: Path
    config: Path
    sources: tuple[str, ...]
    forbidden: tuple[str, ...]

    def run(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(LINT_IMPORTS),
                "--config",
                str(self.config),
                "--contract",
                self.contract,
                "--no-cache",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def write(self, module: str, body: str) -> Path:
        """Put `body` in a module of the probe tree, creating it if need be.

        A package gets a submodule rather than a line in its `__init__`, because
        that is the shape a real violation takes: nobody imports the model server
        from `work/__init__.py`, they import it from the service that needed one
        thing out of it.
        """
        path = _path_of(self.root, module)
        if path.is_dir():
            path = path / "service.py"
            path.write_text(STUB + body, encoding="utf-8")
            return path
        assert path.exists(), f"{module} is not part of the mirrored tree"
        path.write_text(path.read_text(encoding="utf-8") + body, encoding="utf-8")
        return path


def _path_of(root: Path, module: str) -> Path:
    parts = module.split(".")
    directory = root.joinpath(*parts)
    if directory.is_dir():
        return directory
    return directory.parent / f"{parts[-1]}.py"


def _rename(module: str) -> str:
    """`pdm.work` -> `probe.work`; `psycopg` -> `psycopg`."""
    if module == "pdm":
        return PROBE
    if module.startswith("pdm."):
        return f"{PROBE}.{module[len('pdm.') :]}"
    return module


def _modules(raw: str) -> tuple[str, ...]:
    return tuple(_rename(line.strip()) for line in raw.strip().splitlines() if line.strip())


def _create(root: Path, modules: Iterable[str]) -> None:
    """Stand up an importable tree containing every module named."""
    wanted = {m for m in modules if m == PROBE or m.startswith(f"{PROBE}.")}
    packages = {PROBE}
    for module in wanted:
        parts = module.split(".")
        packages.update(".".join(parts[:i]) for i in range(1, len(parts)))
        if any(other.startswith(f"{module}.") for other in wanted):
            packages.add(module)

    for package in sorted(packages):
        directory = root.joinpath(*package.split("."))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "__init__.py").write_text(STUB, encoding="utf-8")

    for module in sorted(wanted - packages):
        path = root.joinpath(*module.split("."))
        path.parent.mkdir(parents=True, exist_ok=True)
        (path.parent / f"{path.name}.py").write_text(STUB, encoding="utf-8")


def _mirror(contract: str, into: Path) -> Mirror:
    parser = configparser.ConfigParser()
    parser.read(REAL_CONFIG, encoding="utf-8")

    section = f"importlinter:contract:{contract}"
    assert section in parser, (
        f"{REAL_CONFIG.name} no longer defines a contract called {contract!r}. "
        "A deleted contract enforces nothing, and lint-imports would still pass."
    )

    real = parser[section]
    sources = _modules(real["source_modules"])
    forbidden = _modules(real["forbidden_modules"])
    assert sources and forbidden, f"{contract} names nothing and so forbids nothing"

    root = into / "tree"
    root.mkdir()
    _create(root, sources + forbidden)

    mirrored = configparser.ConfigParser()
    mirrored["importlinter"] = {
        "root_package": PROBE,
        "include_external_packages": parser["importlinter"].get(
            "include_external_packages", "True"
        ),
    }
    mirrored[section] = {
        "name": real["name"],
        "type": real["type"],
        "source_modules": "\n" + "\n".join(sources),
        "forbidden_modules": "\n" + "\n".join(forbidden),
    }

    config = into / "mirrored.ini"
    with config.open("w", encoding="utf-8") as handle:
        mirrored.write(handle)

    return Mirror(contract=contract, root=root, config=config, sources=sources, forbidden=forbidden)


# ── the trees themselves are sound ────────────────────────────────────────


@pytest.mark.parametrize("contract", ["llm-build-time-only", "domain-touches-no-io"])
def test_the_mirrored_tree_passes_before_anything_is_planted(tmp_path: Path, contract: str) -> None:
    """Otherwise every test below could be passing on a broken fixture.

    A tree that fails the contract for some reason of its own - a missing
    module, a typo in the generated config - would make each exit code 1 below
    mean nothing at all.
    """
    result = _mirror(contract, tmp_path).run()
    assert result.returncode == 0, result.stdout + result.stderr


# ── invariant 1 ───────────────────────────────────────────────────────────
#
# No runtime module imports llm/ (ADR-003). The one that pays for itself:
# runtime determinism stops being an agreement people keep and becomes a thing
# the build refuses.


@pytest.mark.parametrize("source", ["probe.work", "probe.api", "probe.dispatch"])
def test_a_runtime_module_importing_llm_is_refused(tmp_path: Path, source: str) -> None:
    mirror = _mirror("llm-build-time-only", tmp_path)
    assert source in mirror.sources, (
        f"{source} is no longer a source module of the invariant 1 contract. "
        "A runtime package dropped from that list is unguarded, silently."
    )

    mirror.write(source, f"from {PROBE}.llm import draft\n")

    result = mirror.run()
    assert result.returncode == 1, result.stdout + result.stderr
    assert "llm" in result.stdout


def test_reaching_llm_through_an_intermediate_module_is_refused(tmp_path: Path) -> None:
    """The comment in `.importlinter` says indirect paths are checked too.

    `allow_indirect_imports` is not set, and this is what that costs somebody who
    sets it: a runtime module that imports a helper that imports the drafter is
    ADR-003 broken in two hops instead of one, and it is the shape a violation
    would actually arrive in.
    """
    mirror = _mirror("llm-build-time-only", tmp_path)

    helper = mirror.root / PROBE / "helper.py"
    helper.write_text(STUB + f"from {PROBE}.llm import draft\n", encoding="utf-8")
    mirror.write("probe.work", f"from {PROBE} import helper\n")

    result = mirror.run()
    assert result.returncode == 1, result.stdout + result.stderr


# ── invariant 10 ──────────────────────────────────────────────────────────
#
# dispatch() returns the same answer for the same input and touches no
# database (ADR-030). The half the issue called missing: nothing planted a
# database import in a domain module and required the contract to break.


@pytest.mark.parametrize(
    "source", ["probe.dispatch.domain", "probe.work.domain", "probe.triggers.domain"]
)
def test_a_domain_module_importing_the_database_is_refused(tmp_path: Path, source: str) -> None:
    mirror = _mirror("domain-touches-no-io", tmp_path)
    assert source in mirror.sources, (
        f"{source} is no longer a source module of the invariant 10 contract."
    )

    mirror.write(source, f"from {PROBE}.platform import db\n")

    result = mirror.run()
    assert result.returncode == 1, result.stdout + result.stderr


def test_a_domain_module_importing_a_repo_is_refused(tmp_path: Path) -> None:
    """The repo, not only the connection.

    A domain module that goes through `jobs/repo.py` never names `db` and is
    just as far outside the invariant: the argument is that the arithmetic can
    be checked against records written out by hand, and a function that can ask
    the queue a question answers differently on a Tuesday.
    """
    mirror = _mirror("domain-touches-no-io", tmp_path)
    mirror.write("probe.work.domain", f"from {PROBE}.platform.jobs import repo\n")

    result = mirror.run()
    assert result.returncode == 1, result.stdout + result.stderr


def test_a_domain_module_importing_psycopg_directly_is_refused(tmp_path: Path) -> None:
    """The route around every module name on the forbidden list.

    `psycopg` is on it for that reason, and it is why the contract sets
    `include_external_packages`. A domain module that imports the driver itself
    reaches the database without naming anything inside `pdm`.
    """
    mirror = _mirror("domain-touches-no-io", tmp_path)
    assert "psycopg" in mirror.forbidden

    mirror.write("probe.dispatch.domain", "import psycopg\n")

    result = mirror.run()
    assert result.returncode == 1, result.stdout + result.stderr


# ── what the contract does not cover ──────────────────────────────────────


def test_schedule_is_outside_the_invariant_10_contract(tmp_path: Path) -> None:
    """Not a violation, and the point of writing it down.

    `docs/invariants.md` says invariant 10 covers `dispatch()` and not
    `schedule()`: the CP-SAT planner in `dispatch/solver.py` is not a source
    module, and its time budget is wall-clock seconds, which is why one row of
    `docs/results/comparison.md` changed between machines. A reader who assumes
    the contract covers the solver would be wrong, and this is the assertion
    that says so rather than a sentence that can drift.

    If the solver is ever brought inside the contract, this test fails and the
    invariants page is what needs changing.
    """
    mirror = _mirror("domain-touches-no-io", tmp_path)
    assert f"{PROBE}.dispatch.solver" not in mirror.sources

    solver = mirror.root / PROBE / "dispatch" / "solver.py"
    solver.write_text(STUB + "import psycopg\n", encoding="utf-8")

    result = mirror.run()
    assert result.returncode == 0, (
        "the invariant 10 contract now covers dispatch/solver.py. That is a "
        "widening worth having, and docs/invariants.md still says it does not."
    ) + result.stdout

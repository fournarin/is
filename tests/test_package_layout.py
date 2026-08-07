"""The package layout must always match docs/architecture (design.md section 2).

These tests check shape, not behaviour. .importlinter refers to module names as
literal strings, so if somebody renames or deletes a module, every rule naming it
goes quiet instead of failing. That would mean ADR-003 and ADR-030 silently stop
being enforced, which is the one failure mode an import linter cannot catch on
its own.

Rejecting modules outside the list keeps the tree from growing past what the
import rules cover.
"""

import importlib
import pkgutil

import pdm
import pdm.workers

# Must match the module table in design.md section 2. Changing this list is only
# allowed together with a change to that document.
EXPECTED_MODULES = frozenset(
    {
        "contracts",
        "platform",
        "signals",
        "triggers",
        "playbooks",
        "retrieval",
        "llm",
        "authoring",
        "work",
        "dispatch",
        "sinks",
        "sim",
        "api",
        "workers",
    }
)

# ADR-026 splits the worker into two roles that must be able to run as separate
# processes.
EXPECTED_WORKER_ROLES = frozenset({"runtime", "authoring"})


def _submodules(package: object) -> frozenset[str]:
    path = getattr(package, "__path__", None)
    assert path is not None, f"{package} is not a package"
    return frozenset(info.name for info in pkgutil.iter_modules(path))


def test_every_documented_module_exists_and_imports() -> None:
    for name in sorted(EXPECTED_MODULES):
        importlib.import_module(f"pdm.{name}")


def test_no_modules_beyond_the_documented_set() -> None:
    assert _submodules(pdm) == EXPECTED_MODULES


def test_worker_has_the_two_roles_required_by_adr_026() -> None:
    assert _submodules(pdm.workers) == EXPECTED_WORKER_ROLES


def test_every_module_documents_its_role() -> None:
    """An empty module that does not say what it is for is the kind of leftover
    that lessons_carried.md section 4.4 warns about."""
    for name in sorted(EXPECTED_MODULES):
        module = importlib.import_module(f"pdm.{name}")
        assert module.__doc__, f"pdm.{name} has no docstring describing its role"

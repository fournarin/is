"""Every field of the configuration schema is read by something.

`.env.example` states the rule at the top of the file, from lesson 4.4: "config
entries with no consumer create expectations that nothing backs, and the cost of
leaving them shows up at handover. Delete a key the moment it stops being read."
This is that rule as a gate, for `config/` rather than for the environment.

An unread key is not merely untidy. `config/policy.yaml` is the file an operator
is told to edit, and each key in it is a promise that editing it changes
something. A key nothing reads is a promise the system does not keep, and the
person who finds out is the one who set it and then wondered why nothing moved.

`safety_min_score` is the reason this exists and is the one entry allowed below.
It is set to 0.75 in the runtime retrieval profile, with a comment saying that
safety questions use a stricter bar, and `retrieval/service.py` builds both
profiles passing `min_score` alone. A reader of `policy.yaml` would conclude the
system holds a higher bar before answering a safety question. It does not, and
nothing anywhere decides what makes a question a safety question - so this is a
design gap behind a key rather than a key to delete quietly, and it needs a
record either way.

How a field counts as read: its name appears anywhere in `src/`, `scripts/` or
`web/` outside the schema module. That is deliberately loose - it accepts
attribute access, a keyword argument carrying the value on, and a string key -
because the alternative is a data-flow analysis that would be wrong in the other
direction and would have to be argued with every time somebody passed a value
through a function. A name that appears nowhere at all is unambiguous, and that
is the only case this refuses.

**What that looseness costs: a name is not a read.** Any identifier that happens
to share the field's name counts as a consumer, including a function parameter
that the configured value never reaches. A green result here therefore means
"every field's name occurs somewhere", not "every field is used", and the false
pass is the same kind as counting this file, which is why this file excludes
itself. Tightening it is part of #108.

`safety_critical` was the standing example of that gap and is no longer one.
Until ADR-087 it passed only because `work/thresholds.propose` has a parameter of
that name and nothing outside the tests called it; `api/loops.py` now carries the
configured value into the refusal, and a test asks the endpoint for it
(invariant 11). The example is gone; the limitation above is not.

This file excludes itself from the search. It names every allowed field twice,
in the list and in the reason beside it, so counting itself would make every
exception look like a consumer and the gate would pass by describing the problem.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "src" / "pdm" / "platform" / "config" / "schema.py"
SELF = Path(__file__).resolve()

# Fields that carry no consumer today, each with the reason it is still here.
# An entry is a debt with a name on it, not a permission - remove it by making
# the field read or by removing the field.
ALLOWED_WITHOUT_A_READER = {
    # Set in policy.yaml's runtime profile as a stricter bar for safety
    # questions. retrieval/service.py passes min_score alone, and nothing in the
    # system classifies a question as safety-related, so the key describes an
    # intention rather than a behaviour. Delete it or build it; do not leave it.
    "safety_min_score",
}

# Names that are structure rather than configuration.
STRUCTURAL = {"model_config", "version"}


def _schema_fields() -> dict[str, str]:
    """Field name -> the class that declares it."""
    tree = ast.parse(SCHEMA.read_text(encoding="utf-8"))
    fields: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.AnnAssign):
                continue
            if not isinstance(statement.target, ast.Name):
                continue
            name = statement.target.id
            if name.startswith("_") or name in STRUCTURAL:
                continue
            fields.setdefault(name, node.name)
    return fields


def _sources() -> list[str]:
    texts: list[str] = []
    for directory, pattern in (("src", "**/*.py"), ("scripts", "*.py"), ("web", "*.py")):
        for path in (REPO / directory).glob(pattern):
            if path.resolve() in (SCHEMA, SELF) or "__pycache__" in path.parts:
                continue
            texts.append(path.read_text(encoding="utf-8"))
    return texts


def main() -> int:
    fields = _schema_fields()
    sources = _sources()

    unread = [
        (name, owner)
        for name, owner in sorted(fields.items())
        if not any(re.search(rf"\b{re.escape(name)}\b", text) for text in sources)
    ]

    stale = sorted(ALLOWED_WITHOUT_A_READER - {name for name, _ in unread})
    if stale:
        print("Listed as having no reader, but something reads them now:")
        print("\n".join(f"  {name}" for name in stale))
        print("\nRemove them from ALLOWED_WITHOUT_A_READER in this file.")
        return 1

    offenders = [(n, o) for n, o in unread if n not in ALLOWED_WITHOUT_A_READER]
    if offenders:
        print("Configuration fields that nothing reads:")
        print()
        for name, owner in offenders:
            print(f"  {owner}.{name}")
        print()
        print(
            "A key in config/ is a promise that setting it changes something.\n"
            "Delete the field, or read it, or add it to ALLOWED_WITHOUT_A_READER\n"
            "in this file with the reason it survives."
        )
        return 1

    known = len(ALLOWED_WITHOUT_A_READER)
    print(f"{len(fields)} configuration fields, all read ({known} allowed exception(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

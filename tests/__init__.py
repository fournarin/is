"""Makes `tests` a package, so `tests.modes` has one name.

Without it mypy sees `tests/modes.py` as both `modes` (from its own directory)
and `tests.modes` (from the imports in three test files) and refuses to check
anything. The subdirectories deliberately stay without one: pytest walks up only
while `__init__.py` exists, so the test modules themselves are still imported the
way they always were.
"""

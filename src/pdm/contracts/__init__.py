"""The eight data contracts every other module connects through.

This package is a leaf: it must never import another pdm module.
Without that rule the dependency graph becomes a mesh and none of the
other import rules can be expressed (ADR-030).
"""

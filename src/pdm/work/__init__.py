"""WorkOrder lifecycle: creation, playbook binding, completion, shift handover.

Copies the facts the scheduler needs onto the work order at creation time so
that dispatch never has to read a Finding (ADR-030).
"""

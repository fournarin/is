"""Shared infrastructure: Clock, config loader, job queue, auth, audit, ObjectStore.

Clock is the single time port for the whole system. Domain code must never
read the system clock directly (ADR-028).
"""

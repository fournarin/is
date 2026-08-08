"""Background entrypoints, split into two roles by ADR-026.

Split because a twenty-minute manual ingest would otherwise stall ticket
dispatch for the whole system.
"""

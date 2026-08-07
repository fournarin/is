"""Hybrid retrieval over indexed manual chunks.

Used both at authoring time and at runtime: the extractive fallback with page
citations is a runtime path, which is exactly why this is a separate module
from llm/ (ADR-015, ADR-029).
"""

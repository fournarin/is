"""Rule engine. Signals in, Findings out (layer 1).

Covers both detection (threshold already crossed) and prediction
(trend extrapolation to an ETA, ADR-020). Findings have a lifecycle and a
suppression window that prevents alarm floods (ADR-023).
"""

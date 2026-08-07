"""Language model access. Build time only.

Importable from authoring/ and nowhere else, enforced by .importlinter
(ADR-003). The api container also has no network route to llm-server, so the
rule holds at two independent layers (ADR-029).
"""

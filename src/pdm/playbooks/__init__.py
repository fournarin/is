"""Playbook store and the runtime serving order (layer 2).

One row per (symptom_code, machine_model); no version chain. History lives in
WorkOrder.playbook_snapshot instead (ADR-018). Draft playbooks are never
served at runtime, not even when there is nothing else to give the technician.
"""

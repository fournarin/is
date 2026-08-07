"""worker-runtime: trigger loop, dispatch tick, reaper, job_class=runtime.

Must never pick up a job_class=authoring job (invariant 12).
"""

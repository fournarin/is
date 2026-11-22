# Phase 3 set 2 - PASSED (Cowork, 2026-11-16 23:20)
EHS (s2r3-safety.md): supervised real-machine trial = YES with conditions. N1, N3, N4, N5, B5 closed with tests
that reproduce the holes; W017 hot step correct. Cowork measured the set-2 SSR pages directly: no h-scroll, no
clipped text at 360/390; offline tag no longer clips the station name; offline note at the top of energy steps.
## Safety carry-over (do FIRST in the next Claude Code round, each with a test)
C1. Witness must not be the lock owner (a supervisor cannot witness their own release).
C2. Witness password: rate limit + audit of failed attempts; never kept on the technician's phone (no
    autofill / remembered field); consider a short PIN per shift lead instead of the account password.
C3. A witnessed release after a "still locked" close must also require the restore checks.
C4. Test the window between handover and the shift lead's re-assignment (N2 lock-on before lock-off).
C5. Per-machine advisory lock: confirm the API connection is NOT autocommit for these writes, add a
    two-connection race test, and take the same lock when moving to the next step.
## Trial conditions (for the report and for any real-machine use)
One line/cell, one or two technicians per job; handovers only with the shift lead present; the plant's paper
LOTO procedure stays the authority; a safety officer present; database migrated with the 0022 test passing.

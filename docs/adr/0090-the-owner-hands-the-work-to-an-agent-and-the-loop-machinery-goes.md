# ADR-090: The owner hands the work to an agent, and the loop machinery goes

Written on 2026-09-27, 25 days before the feature freeze. Supersedes
[ADR-085](0085-what-the-unattended-loop-may-merge-and-a-check-that-can-stop-it.md)
in full. Supersedes the parts of
[ADR-052](0052-what-review-was-protecting-and-what-it-was-not.md) and
[ADR-086](0086-what-this-term-does-not-do.md) that concern who merges and what
the backlog carries. The scope decisions of ADR-086 stand unless a later record
reopens one.

## Context

On 2026-09-27 the owner reviewed the term's work and found it had drifted. Of
the last ten merged pull requests, six were about the repository's own process:
the invariants table, the loop's protocol, the ledger, and documents about
documents. Every one of the eight issues still open for the term was of the
same kind. Meanwhile the thing a technician would meet first was weak. After a
rehearsal, one playbook is approved. The drafter picks the wrong page for two of
the three repairable symptoms, and writes a six-step procedure for a symptom the
manuals say nothing about.

The governance was the cause, and it was working as written:

- The unattended loop could not merge anything that touched `docs/invariants.md`,
  `migrations/`, `.github/workflows/` or `.claude/` (ADR-085 §2). Most
  meaningful work touches one of these, so most work waited on a person.
- `human-review` on an issue made the issue ineligible for the loop (ADR-085
  §1). By 20 September every remaining issue carried it, and the loop opened
  "backlog empty" (#126) and did nothing further.
- The loop itself was switched off twice for cost. The second time was on
  2026-09-22 and it stayed off. A watchdog workflow then opened #127 about the
  silence, which is the watchdog reporting the owner's own decision back to
  them.
- `CLAUDE.md` was 17 KB, mostly field-level contract text repeated from the
  ADRs. It did not contain the commands an agent actually runs, and it asked
  for a plan to be approved before any substantial edit.

The owner's instruction, 2026-09-27: act as the owner of the work received from
the advisor, decide without asking, aim for the best result, and keep the cloud
routine off because usage is scarce.

## Decision

1. **An interactive session owns the work.** It decides, builds, tests and
   merges its own pull requests when CI is green. It does not ask for plan
   approval. The protocol is [`.claude/autonomy.md`](../../.claude/autonomy.md),
   rewritten to ten rules.
2. **The unattended loop and its machinery are removed.** The removed files
   are `.claude/routine-prompt.md`, `.github/workflows/is-the-loop-alive.yml`,
   `config/cadence.yaml`, `scripts/check_the_loop_is_alive.py` and its test.
   The routine on claude.ai stays disabled.
3. **`human-review` is kept for one case only**: a safety-relevant constant with
   no source (autonomy rule 8). Path-based merge restrictions are dropped. CI
   is the gate, and CI already checks the invariants' mechanisms.
4. **ADRs record decisions about the system, not about process.** Numbers are
   no longer reserved on issues. The next number is one above the highest on
   `main` and on open PR branches.
5. **`CLAUDE.md` is short and operational**: the brief, the goal, the
   principles, a map of the code, and the commands. The data contracts move
   unchanged to [`docs/contracts.md`](../contracts.md).
6. **Priority for the remaining weeks is what a technician or the report
   sees**, in this order: correct drafting and more playbook coverage; loading
   real data from files (signals, roster, skills, shifts); proving backup and
   restore; the technician trial. The process issues #111, #112, #114, #115,
   #116 and #117 are closed as not worth the remaining weeks, along with #126
   and #127.

## Reasons

**The constraint was never a lack of care. It was a lack of finished work.** The
review that ADR-052 and ADR-085 protected is still there, in a stronger form:
CI runs every invariant's mechanism and, since ADR-088, a test that breaks each
one. A person reading a diff after that adds little, and a person who is never
available adds nothing but delay.

**Several sessions run at once.** On the day this was written, two sessions
edited the same working tree and one switched branches under the other. Rule 3
(each session in its own `git worktree`) is the cheapest fix for that, and it is
the kind of rule that belongs in the protocol rather than in an ADR.

**`docs/decisions-to-defend.md` stays, as preparation for the report and viva,
not as a merge gate.** The questions it answers will still be asked.

## What would reverse this

If an agent merges something that CI passed and that was wrong in a way a
person would have caught, the fix is a new check. If no check can be written
for that class of error, reinstate human review for that class only.

# ADR-003: The LLM does not write repair instructions at runtime

## Context

The advisor said "there are only manuals, use RAG", which settles the retrieval
question. But the output is repair instructions a technician will carry out on
machinery in a vehicle assembly plant.

## Decision

Use RAG and an LLM at **build time** to draft playbooks from the manuals, have an
engineer review and approve each one, and serve only approved playbooks at
runtime. Where no playbook exists, fall back to an extractive span with a page
citation.

## Reasons

A wrong torque value or a wrong lockout order is a risk to a person. Generating
at runtime hands the technician text nobody has ever read, with nobody in a
position to catch it in time. Moving the LLM ahead of the work, with a person in
between, gives deterministic output, fast responses, and someone accountable for
every page.

**On communication:** present this to the advisor as *still RAG, as instructed* -
with an approval step added before anything reaches a technician - rather than as
a change of method.

## Consequences

A review and approval screen is required, full provenance must be stored, and
there must be a mechanism for what happens when a manual is updated (mark for
review, never silently delete).

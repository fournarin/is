# ADR-016: `component` is a label in configuration, not an entity in the database

## Context

ADR-009 established that `Finding.component` comes from the rule's definition but
did not say how the label is stored. The author's earlier system had `Component`
and `ComponentAlias` as real tables; they were cut from the product because they
could not be made to work. The main reason was that **manuals are tied to
machines, not to parts**.

## Decision

No part entity, no table, no alias resolution. `component` is a label drawn from a
list declared per machine model **in the same configuration file that declares the
rules**, validated on load: a rule naming a label outside the list stops the boot.

## Reasons

1. Manuals are indexed at machine level, so a part-level index has nothing to
   index and would require inference, which ADR-009 already rejected.
2. Master data with no owner becomes master data that is wrong, which is worse
   than none, because the system then appears to know. Forty machines by thirty
   parts is 1,200 rows nobody maintains.
3. Nobody has the authority to define a standard parts list. Manuals contain
   parts lists by order number, which is not the unit a technician repairs.
4. No layer in this system needs it. Layer 1 rules fire independently, layer 2 is
   keyed by `symptom_code` and `machine_model`, layer 3 queues by
   machine, line, severity and skill.
5. The label sits next to the rule that uses it, so the two cannot age apart.

## Consequences - this narrows ADR-009 and sharpens it

The answer to "which part" comes **entirely from the signal side** (the rule's
label plus its evidence), not from the document side. Retrieval must therefore
never filter by part, and layer 2 stays keyed at machine level. The two sides do
not have to meet, which makes both of them simpler.

The question to the plant still needs asking, but what is being requested is **a
map of labels**, not a parts register, and it comes from the tag list and the
electrical drawings rather than from the manuals.

**Revisit if:** the plant wants failure statistics per part across machines
(MTBF per part). That would need a canonical component, and it would have to be
the plant's taxonomy rather than one we invented.

# ADR-133: The screens are rebuilt on one design system, with Lucide and React Aria

Written on 2026-11-16. Extends ADR-093 (screens each role already knows) and
ADR-008 (no new dependency without an ADR). Decided by the agent on the owner's
delegation (ADR-090), after the owner passed the design system at GATE 2.

## Context

The first screens were built slice by slice, and stakeholders read them as a
generic admin template: emoji for icons, blue bars and pastel pills, a phone
column stretched across a desk, grey text under 7:1, and Thai broken inside
words ("ของตัว | เอง"). A redesign was run outside the repository
(`ui-redesign-work/design/`): six stakeholder simulations, a requirements list
with acceptance criteria, three concepts, a panel review and a measured design
system (tokens, components with states, every screen at its viewports). The owner
passed it at GATE 2 on 2026-11-16. The screens are rebuilt from it in seven
sets; this record covers the foundations every set uses.

## Decision

1. **One visual system**, defined in `web/app/ui/v2/v2.css` and scoped under
   `.v2` while the screens of later sets still read `globals.css`: one canvas,
   one work surface, ink as the only action colour, every text pair >= 7:1;
   amber means a machine over its threshold (solid) or forecast to be (outline)
   and nothing else; separation by surface and space, outlines on inputs only;
   one callout form (a leading icon whose colour carries the meaning, no stripe).
2. **Type.** IBM Plex Sans Thai Looped, weights 400 and 600, self-hosted by
   `next/font` at build time like the existing face. Phone screens never go
   under 18 px (REQ-G-06).
3. **Thai breaks only between words** (`web/lib/thai.ts`): the server cuts Thai
   with `Intl.Segmenter`, a glossary of plant compounds vetoes splits inside
   them, codes and number + unit stay whole, and each piece is a nowrap span.
   The screen checks read text through `readable()`, which unwraps these spans,
   so every assertion still matches what a person reads.
4. **Icons: `lucide-react` 1.49.0** (ISC). One drawn set on a 24 px grid with a
   2 px stroke replaces emoji. Always beside a word; no warning triangle outside
   an ISO 7010 sign.
5. **Accessible controls: `react-aria-components` 1.22.1** (Apache-2.0) for
   controls the platform does not give whole - radio groups, dialogs, menus -
   so focus, keyboard and screen-reader behaviour come from a maintained
   library rather than from each screen.
6. **The synthetic-data banner** (REQ-G-11) reads the same `SIGNAL_SOURCE` the
   runtime worker reads; anything but `replay` shows it.

## Consequences

- Two runtime dependencies, both pinned exactly. Lucide ships only the icons a
  page imports; React Aria loads only on the client components that use it.
- Until set 7 the old and new styles live side by side. A class name shared by
  both files leaks: v2 classes that collided are prefixed (`v-card`, `is-ok`),
  and `.v2` resets the bare elements `globals.css` styles.
- The look is measured, not asserted: the redesign's checks (contrast, tap
  targets >= 56 px on phones, horizontal scroll, clipped inputs, text overlap,
  Thai words on two lines) run on every rebuilt screen at its viewports.

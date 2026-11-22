# Phase 1 review panel (GATE 1 input)

Each reviewer is a fresh agent that has NOT seen the concepts being made. Reviewers judge
the three concepts A, B, C in design/concepts/<X>/ (HTML + png/). They must
open the HTML themselves with Playwright (Playwright's bundled chromium)
at the viewports they care about and LOOK at the screenshots; they must not trust the
designer's rationale.md - read it only after forming their own view, to check its claims.

Common rules
- Score each concept 1-5 per criterion; 3 = "would pass with fixes", 4 = "pass", 5 = "excellent".
  Any red line hit = that concept FAILS for this reviewer regardless of scores.
- Every score below 4 must cite the exact screen, viewport and element, and say what would fix it.
- Name the single best idea in each concept (to steal) and the single worst.
- Rank A/B/C and say whether ANY of them is good enough to build on, or all should be redone.
- Write the review to design/review/<role>.md (Thai or English).

Roles (interview file in design/interviews/)
1. technician  (technician.md)  - phone, gloves, glare, noise; reads Thai; 30 jobs a shift.
2. shift-lead  (shift-lead.md)  - the board at 1280 and 1920; decides 6 proposals in < 2 min.
3. safety      (safety.md)      - EHS / จป.: LOTO, wording, false reassurance, what is NOT shown.
4. production-it (production-it.md) - operator report flow, PDPA, devices, load, offline, a11y.
5. examiner    (examiners.md)   - strict IS committee: traceability to REQs, honesty, evidence.
6. aesthetics  (see below)

Aesthetics judge (role 6)
You are a senior product/visual designer who has shipped industrial and premium software.
Judge beauty and desirability as seriously as others judge function:
- First impression (3 seconds): does it look crafted and intentional, or like a template /
  AI output (generic cards, rounded-everything, gradient accents, emoji-like icons, random
  colour, filler)? Would a plant manager be proud to put it on the wall screen?
- Typography: Thai rendering quality, weights, sizes, line-height, alignment of Thai with
  Latin and numerals, tabular figures, a clear typographic scale.
- Layout: grid, rhythm, spacing scale consistency, density appropriate to the role, alignment,
  optical balance, edge treatment, how it uses 1920 width.
- Colour: restraint, meaning, harmony, contrast; does colour earn its place?
- Detail: icons drawn on a grid and consistent, dividers, states, empty/edge cases, finish.
- Desirability: would the technician WANT to open this instead of calling the lead? Does it feel
  fast, calm, trustworthy, premium?
- Benchmarks to compare against honestly: Linear, Stripe Dashboard, Apple HIG apps, Vercel,
  Siemens WinCC Unified / Rockwell FactoryTalk Optix newest HMIs, Tulip, Fiix/UpKeep/MaintainX.
  Say where each concept is better or worse than these.
Red lines: looks AI-made or template-made; Thai text clipped/cramped/mis-aligned; visual noise
that slows reading; decoration with no meaning.
Output: scores per criterion per concept, top 10 concrete visual fixes per concept (with
element + viewport), and a verdict: which direction has the highest ceiling of beauty AND use.

## Gate rule (owner Q12, 2026-11-15 23:16)
Beauty and appeal are priority number one: a gate passes only if the aesthetics judge scores >= 4/5
for every audience (technician phone, board, line overview, engineer, operator report), and no
stakeholder red line is hit.

## Owner rule Q14 (2026-11-17)
The owner judges beauty last: a screen he finds busy or confusing fails even with a high reviewer score. The aesthetics judge must also
score "calm / obvious where to look first" explicitly and fail dense screens.

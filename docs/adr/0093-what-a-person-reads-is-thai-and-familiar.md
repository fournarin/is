# ADR-093: What a person reads is Thai, and shaped like what they already use

Written on 2026-09-27, after the owner's trial (ADR-092) failed on the screens.

## Context

The owner ran the trial and stopped: the screens were confusing. The users are
Thai technicians, and they asked for Thai that is easy to follow and a system
people would want to open. Reading the live stack showed why:

- **Every sentence the backend wrote was English.** A technician was shown
  "MC-012 unknown: SYM-002 detected by R-safety-interlock-open". The shift lead
  was shown "severity is critical; the line loses about 270 unit(s) while this
  waits". ADR-005 was followed to the letter, since every ticket explains itself,
  but not in a language the reader speaks. The explanation was built out of
  identifiers.
- **Times were written in UTC** in a plant that runs on Bangkok time.
- **The screens showed the project's own vocabulary**: slice numbers, ADR
  numbers, "playbook". Each role also landed on a menu of screens instead of
  on its work.

## Decision

1. **Every sentence a person on the floor reads is Thai.** This covers the
   reasons on work orders, the scheduler's priority reasons, the shift summary,
   the reasons work is held back, and the explanations of a placement. Code,
   logs, identifiers, API field names and the repository stay English.
2. **One vocabulary, in `pdm/contracts/wording.py`.** Severity, load, durations
   and plant-clock times are written in one place, so `work/` and `dispatch/`
   phrase the same fact the same way. The backend still writes every sentence
   (ADR-005). The web layer only translates fixed codes to labels, such as a
   status or a severity, and never composes a reason.
3. **Names come from configuration.** Each rule and PM task gets a `title`, the
   symptom as a technician would say it. `plant.yaml` gets `skill_names`.
   Titles carry no threshold figures, so tuning a threshold (ADR-073) cannot
   leave a stale number in a name. A missing title shows as "อาการรหัส SYM-…",
   visibly unnamed rather than invented.
4. **Times are on the plant's clock**, from `plant.yaml`'s timezone.
5. **Each screen copies a pattern its user already knows**, so nothing has to
   be learned:
   - the technician gets a ride-hailing driver's flow: one job at a time, then
     accept, in progress and done, with steps as a checklist and big buttons;
   - the shift lead gets a whiteboard of columns, with confirm in one tap;
   - the engineer gets document sign-off, with the draft beside the manual page;
   - the operator gets a short message form: pick the machine, pick what is
     wrong, send.
   Every work order also prints on one page, because the plant still runs on
   paper and a printout is the bridge from it.
6. **Notification through LINE is not built this term.** It is the most familiar
   channel of all. But it sends plant information through a third-party cloud,
   which the NDA behind ADR-029 rules out without the plant's IT agreeing. If it
   is ever built, it goes through the layer-4 adapter (ADR-012) and sends only
   "new job at station 3" with a link back into the plant network, never the
   manual's content.

## Consequences

- A reason recorded before this change stays in English on that order, because
  `reason` is written once. The demo is re-seeded, so this affects no real data.
- The "seen N times" count is no longer frozen into the reason. The screen
  reads it live through `finding_ref`, which is where it was always correct.
- Tests assert the Thai phrases. A change in wording is now a visible test diff,
  which is how it should be for text a person acts on.

# The design record for the second-generation screens

Kept here as it was made, between 15 and 18 November 2026, before the screens
were built into `web/` ([ADR-133](../adr/0133-the-screens-are-rebuilt-on-one-design-system.md)
to [ADR-144](../adr/0144-end-to-end-flows-and-an-accessibility-scan-in-the-repo.md)).

- [REQUIREMENTS.md](REQUIREMENTS.md) - the 107 requirements, each with its source.
- [TRACEABILITY.md](TRACEABILITY.md) - requirement -> screen -> test, with the status the build showed.
- [system/](system/README.md) - the design system: tokens, fonts (IBM Plex, [OFL](system/fonts/OFL-plex.txt)),
  the static screen mockups in `screens/`, their renders in `png/`, and one spec page per screen in `spec/`
  (open `spec/index.html`). Manual pages in `assets/` are from `fixtures/corpus/r-2000ic-maintenance.pdf`.
- [review/](review/) - every review round: the reviewers' briefs, their findings and the summaries that closed them.

Two things differ from the working copy. The script that rendered the mockups and
measured them is not included; the measurements it wrote are in each spec page.
The external trial participant is named by role ("ผู้ทดลองภายนอก"), not by name.
Paths in the review notes were working-folder paths; they are relative here, and
some point at working material (interviews, concepts) that stayed outside the
repository.

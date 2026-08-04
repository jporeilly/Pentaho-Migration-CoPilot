# Version

**1.44.8** - 2026-08-04

**Both fixes in this release came out of chasing a single number.** The
statement demo's release gate reported "18-23% of each page differs",
and following that percentage to its cause found two unrelated things:
one a real conversion defect on 40% of the corpus, one not a defect at
all.

**Crystal's date special fields now keep the format the report
authored.** Print date, data date and modification date carry a
`DateFieldFormat` like any other date, but they have no value type to
match on, so the authored pattern was dropped and the render fell back
to a default - Crystal printed "August 04, 2026" and we printed
"Aug 4, 2026". This was never one demo's cosmetic: **61 of the 150
corpus reports author such a format**, 56 of them `MM/dd/yyyy`, and
every one of them had been rendering as the default. The authored
pattern contains a comma, which has to survive PRD's comma-delimited
`$(name, type, format)` template - verified through the real engine
rather than assumed.

**The gate names a paper-size mismatch instead of burying it in a
percentage.** The rest of the difference is that the two renders are on
DIFFERENT PAPER: the SAP viewer exports A4 - the machine's default
printer - while the report itself specifies Letter. Measured, not
assumed: top-anchored content sits at identical absolute positions
(the invoice table header at y419.3pt in the original, y419.5pt in
ours), while the page-footer band is anchored to the BOTTOM edge -
153pt from it in the original, 154pt in ours - so the taller sheet
pushes it 50pt down the page, and A4's narrower width clips the logo.
None of that is a conversion defect. `compare_renders` now emits an
`info` `paper-size` finding naming both sheets and the two effects they
have on content, so a consultant reads the appearance number for what
it is. The honest limit is stated with it: this is a REPORTING
improvement - the appearance check still counts those cells, because
normalising them away would blind it to genuine bottom-anchored
defects.

Phase 1 remains complete — Informatica PowerCenter, SAP Crystal
Reports, Talend, and Pentaho Xactions (all three definition dialects);
the agent stack (review + consultant reports) covers every family.
See [CHANGELOG.md](CHANGELOG.md) for history.

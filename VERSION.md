# Version

**1.44.1** - 2026-08-01

**The agent stack now covers every family.** 1.44.0 closed the corpus2
gap list for reports; this release brings the Crystal-side agent
experience to Informatica and Talend, and makes the converter fix the
classic silent ETL defect instead of only flagging it.

**The 🛡 ETL review agent** is the release gate's counterpart for
transformations. With no "rendered original" to compare, the
deterministic evidence is the converted graph itself: unmapped steps
(grouped by type, each with its suggested PDI approach), untranslated
and review-flagged expressions, hop integrity (dangling endpoints,
isolated steps), sorted-input hazards on EVERY input leg, placeholder
connections, an optional Pan run through a real PDI install, and a
measured CSV parity result when the diff harness has one. SHIP or
REVIEW is decided by error findings alone; the LLM only annotates
findings with resolution-or-guidance notes. The Generate page gates the
.ktr download on the review, the project page sweeps every stored
mapping and persists SHIP/REVIEW verdicts per row, and ONE consultant
document per mapping — costed action plan first, findings with
evidence, what converted — shares the Crystal consultant stylesheet, in
HTML and Markdown from a single plan builder.

**The converter now INSERTS the Sort rows steps PDI needs.** Group By,
Merge Join and Unique rows run green on unsorted input and produce
silently wrong results — the source engines sorted internally. The
mapper synthesizes a Sort rows step on every unsorted leg with the keys
the target actually needs (group keys; per-leg join keys, both legs of
a join), marked review with a note saying why it exists. Keys the
export cannot reveal leave the honest finding in place rather than a
sort that sorts nothing. The insertion and the review lint share one
semantics table, so the fix and the check can never drift.

**Defaults open the report with data.** A converted report's authored
parameter defaults were written against the original estate's database;
on the demo connection they can be perfectly set and still select
nothing. The API layer now probes the query with the substituted
defaults and, when nothing comes back, repoints the date window at the
data's own MIN/MAX span for the selected defaults — noted as applied
work with the authored window quoted, review flagged. General logic:
any date parameters bounding one date column, any report.

**Staged progress everywhere, and demo polish.** The release gate's
staged background-job pattern is now one JobStore and one StageBar
component: ETL convert, expression translation in both families, the
review agent and the project sweeps all show the same named-stage
progress bar. Wireframe labels clip to their element's box so a long
field name never overlaps its neighbour, the Download actions read in
workflow order with the consultant report last, the
release-check-not-available message is a readable note, and a helper
script runs the API in a visible console so an audience can watch the
calls. Also fixed: a code-motion regression had left the Crystal
release-gate endpoint bound to a helper function — the staged gate was
unreachable; it is restored and re-verified.

Phase 1 remains complete — Informatica PowerCenter, SAP Crystal
Reports, Talend, and Pentaho Xactions (all three definition dialects).
See [CHANGELOG.md](CHANGELOG.md) for history.

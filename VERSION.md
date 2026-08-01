# Version

**1.44.5** - 2026-08-01

**The production list is closed.** The review agent's consultant report
now downloads as a branded PDF - verdict, costed action plan and
severity-coloured findings leading the document, with the header naming
the real source family. The project store is portable: export a
consistent snapshot from one machine's Project page and import it on
another, through sqlite's own backup API in both directions, with the
current store backed up beside itself and non-database uploads refused
with the reason. The ETL family tables scale like the reports table -
per-family name filters and Agent-verdict chips turn a 148-mapping
estate into a worklist - and the last conversion survives a browser
refresh, restoring with an honest note about which actions need the
file re-uploaded.

Together with 1.44.3 and 1.44.4 this completes the production-hardening
round: estate mode, the deliverable pack, persisted gate verdicts,
green CI, Complete/Custom installation, the dependency doctor, the
render queue and the demo-box image.

Phase 1 remains complete — Informatica PowerCenter, SAP Crystal
Reports, Talend, and Pentaho Xactions (all three definition dialects);
the agent stack (review + consultant reports) covers every family.
See [CHANGELOG.md](CHANGELOG.md) for history.

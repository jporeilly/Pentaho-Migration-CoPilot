# Version

**1.44.3** - 2026-08-01

**The engagement runs end to end in the app.** Estate mode batch-converts
a whole selection of exports into the project store from the Project page
- PowerCenter/Talend XML, RptToXml dumps, .rpt binaries, .xactions and
solution zips, routed by content with staged progress, per-file failures
as findings, sources persisted so sweeps and re-opens outlive the
browser. One button then builds the deliverable pack: every artifact
re-converted, each beside its consultant report, the portfolio reports,
and a manifest where failures are listed rather than silently missing.
Release-gate verdicts persist into the store (a Gate chip beside Triage
and Parity), the installer offers Complete and Custom installation
types, and CI is green again - including a real portability fix so
engagement stores carrying Windows paths resolve on any machine.

Phase 1 remains complete — Informatica PowerCenter, SAP Crystal
Reports, Talend, and Pentaho Xactions (all three definition dialects);
the agent stack (review + consultant reports) covers every family.
See [CHANGELOG.md](CHANGELOG.md) for history.

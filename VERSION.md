# Version

**1.34.0** — 2026-07-25

**Phase 1 COMPLETE** — Informatica PowerCenter, SAP Crystal Reports, and
Talend. This round closes the last Crystal manual step: **cross-tab grids
are recovered straight from the .rpt binary** (`report-crosstabs`, via
rpt-rs) instead of being hand-written, so 12 cross-tabs across 10 corpus
reports now convert to live PRD crosstabs — corpus triage 105 READY of 150.
The Windows defect that blocked rpt-rs was fixed and contributed upstream
(MrSrsen/rpt-rs#1).
See [CHANGELOG.md](CHANGELOG.md) for history.

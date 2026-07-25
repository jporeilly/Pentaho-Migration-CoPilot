# Version

**1.24.0** — 2026-07-25

**Phase 1** — Informatica PowerCenter & SAP Crystal Reports complete;
Talend in progress. The layout/schema round: the **layout preview is tabbed
for subreports** (Main report + a tab per converted subreport, showing its
own bands), PK/FK discovery reads `pg_catalog` (a read-only report user is
privilege-filtered out of `information_schema` and saw *no* keys), clearer
🔗 FK badges, and a taller, un-squashed layout preview.
See [CHANGELOG.md](CHANGELOG.md) for history.

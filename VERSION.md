# Version

**1.18.0** — 2026-07-24

Phase 2 multi-source in progress — Talend + Crystal Reports shipped. New:
the **schema-aware SQL agent** — report SQL is EXPLAIN-validated against the
live JNDI target before PRD ever opens it, and a schema-grounded chat on the
Inspect page answers join/column questions and proposes corrected SQL as a
reviewable diff (never auto-applied). Crystal also rewrites blocked idioms
into native PRD report functions (running totals, whole-formula aggregates).
See [CHANGELOG.md](CHANGELOG.md) for history.

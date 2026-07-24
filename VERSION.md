# Version

**1.17.0** — 2026-07-24

Phase 2 multi-source in progress — Talend + Crystal Reports shipped. Crystal
now rewrites blocked idioms into native PRD report functions instead of only
advising: running-total variables become ItemSumFunction / ItemCountFunction
and whole-formula aggregates become Total* functions, review-flagged. Also:
alias-aware record-selection folding (Command-based prompts now filter live),
our own forked extractor, Crystal-faithful page layout, and chart migration.
See [CHANGELOG.md](CHANGELOG.md) for history.

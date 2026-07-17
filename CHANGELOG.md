# Changelog

All notable changes to Migration Copilot are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning follows [SemVer](https://semver.org/).

## [0.1.0] — 2026-07-17

### Added

- Deterministic PowerCenter XML parser: mappings, transformations, fields, port expressions
  (passthrough ports skipped), and instance-level hops into a normalized Pydantic IR.
- Rules-library mapper (`rules/powercenter_to_pdi.yaml`): 16 transformation-type mappings,
  each with `auto` / `review` / `manual` confidence; unknown types routed to manual handoff,
  never guessed. Untranslated expressions downgrade `auto` steps to `review`.
- KTR generator: step types, hops, layout, and confidence/TODO annotations in step
  descriptions; real per-step config for Table Input (SQL), Table Output, Sort rows,
  Group By (keys + SUM/AVG/COUNT/MIN/MAX aggregates), and Modified Java Script placeholder
  with typed output fields.
- Static migration report: auto/review/manual step counts and untranslated-expression count.
- CLI `pdi-migrate` with `parse` and `convert` commands.
- FastAPI layer with dark-themed review UI at `/`: drag-and-drop a PowerCenter export,
  inspect steps with confidence badges, download the generated .ktr. Swagger at `/docs`.
- Sample PowerCenter export (`samples/m_load_sales.xml`); 17 tests.

### Not yet implemented (stubs)

- LLM expression translation (Informatica expression language → PDI).
- Runtime diff harness (run old vs. new on sample data, diff outputs).
- Config emission for Merge Join, Stream Lookup, Insert/Update, Switch/Case.
- PowerCenter Workflow/Session (≈ PDI Job) conversion — out of Phase 0 scope.

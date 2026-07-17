# Changelog

All notable changes to Migration Copilot are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning follows [SemVer](https://semver.org/).

## [0.2.0] — 2026-07-17

### Added

- **React review UI** (Vite + React 18, `frontend/`): dark theme, drag-and-drop upload,
  KPI stat tiles, SVG pipeline flow diagram (longest-path layering, confidence-colored
  nodes), filterable steps table, .ktr preview + download, "Try the sample" button.
  Built bundle served by FastAPI at `/`; replaces the vanilla static page.
- **Real-world corpus**: 11 genuine PowerCenter 10.x exports from the public
  HHS/Informatica GitHub repo in `samples/informatica/` — 110 real mappings, 1,045 steps.
  All parse cleanly (including a 522 KB mapping with 589 connectors).
- **Gap analysis**: `pdi-migrate gaps <dir>` batch-converts a corpus and reports mapper
  coverage — auto/review/manual rates and per-source-type gap list, unmapped types first.
  First run on the real corpus: 53% auto, 1 unmapped type.
- `GET /sample` endpoint; `ConversionResult` API model (pipeline + report + ktr).
- **Build tooling**: `Makefile` (Linux/macOS, or Windows with make) and mirrored helper
  scripts `scripts/dev.ps1` (Windows 11) / `scripts/dev.sh` (Linux) — setup, test, run,
  convert, gaps, ui-install/ui-build/ui-dev, status, clean.

### Fixed

- Rules library: real 10.x exports use transformation type `Sequence`, not
  `Sequence Generator` — both now map to PDI Sequence (found by gap analysis).

### Changed

- Per-step KTR config emission for Table Input (SQL), Table Output, Sort rows,
  Group By (keys + aggregates), and script placeholder steps (was skeleton-only).
- `INSTALL.md` moved to `docs/`.

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

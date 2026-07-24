# ETL Migration Best Practices

Field-tested guidance for PowerCenter → PDI migrations, baked into how Migration
Copilot works. Read this before your first real conversion.

## 1. Inventory before you migrate

- Export **everything** first and run `pentaho-migrate gaps` across the whole folder — the
  coverage report tells you the true auto-conversion rate and every unmapped construct
  *before* you commit to a timeline.
- Rank mappings by business criticality × conversion confidence. Migrate high-confidence,
  low-risk mappings first to build momentum and trust in the process.
- Identify shared objects (mapplets, reusable transformations, common lookups) — convert
  them once, early, not repeatedly.

## 2. Migrate the common 80% flawlessly; hand off the rest

- Discipline matters more than coverage: resist customizing the tool for every
  customer-specific one-off. A clean, explicit manual-handoff list beats a risky guess.
- Never trust a conversion the tool marked `review` or `manual` without a human look.
  The confidence levels exist to direct attention, not to be ignored.

## 3. Test in a sandbox — always

- **Never point converted output at production.** Use the generated sandbox kit
  (connection guide, DDL, synthetic data) for first runs.
- Progress in stages: synthetic data → masked production sample → full-volume test.
- Watch for the classic silent killers: unsorted input into Group By / Merge Join,
  NULL handling in translated expressions, sequence restart behavior, and dialect
  differences in SQL overrides.

## 4. Prove parity, don't assume it

- Define "done" as **output parity**: same input → same output, row for row, old vs new.
- Compare row counts first, then checksums/aggregates per column, then spot-check rows.
- Keep parity evidence per mapping — it's your sign-off artifact and your audit trail.
  (The upcoming diff harness automates exactly this.)

## 5. Plan orchestration separately

- Workflows, sessions, schedules, dependencies, and error handling do **not** convert
  with the mappings. Inventory them and design the PDI Job (.kjb) layer deliberately —
  it's often an opportunity to simplify years of accreted scheduling logic.
- Session-level settings (commit intervals, error thresholds, connection overrides)
  must be consciously re-decided in PDI, not assumed.

## 6. Manage state and sequences

- Informatica persists sequence values and mapping variables in its repository; PDI
  does not by default. Back production keys with database sequences and set starting
  values explicitly from the legacy system's current state at cutover.

## 7. Cut over deliberately

- Run old and new **in parallel** for at least one full business cycle, comparing outputs.
- Have a rollback plan that does not depend on the thing you just migrated.
- Freeze changes to the legacy mappings during migration — or re-run the conversion on
  the final export, not a stale one.

## 8. Keep the audit trail

- Version-control the source exports, the generated .ktr files, and the migration
  reports together.
- Every hand-edit to generated output should be visible in a diff — convert, commit,
  then edit; never edit-then-lose-the-baseline.

## 9. Crystal Reports: treat reports as their own family

Reports are documents, not dataflows — different risks, different checklist:

- **Extract, scrub, then share.** RptToXml copies connection credentials out
  of `.rpt` files into the dumps. Always run `pentaho-migrate report-scrub` on a
  dump folder before committing it to a corpus or attaching it anywhere.
- **Baseline the whole estate first**: `pentaho-migrate report-gaps <dir>` gives
  parse coverage, formula auto/review/manual rates, and the portfolio effort
  number before you commit to a timeline.
- **Validate every generated bundle** with `--validate` (real engine load),
  and open a sample visually in Report Designer — engine-valid proves it
  parses, eyes prove it looks right.
- **Formulas follow the ETL rule**: deterministic first, LLM assist only for
  what rules cannot prove, every AI translation flagged review. Running
  totals and aggregates are *report functions* in PRD, not formulas — when
  the Crystal formula matches a known idiom (a running-total variable, or a
  whole-formula `Sum`/`Count`/`Maximum`/`Minimum`), the converter generates
  the PRD function itself and flags it review; anything less mechanical stays
  a manual work item with the recommended function named in the report.
- **Review rewritten running totals for reset semantics**: Crystal shared
  variables persist across groups and subreports; the generated
  `ItemSumFunction` runs report-wide by default. If the original balance
  reset per group, add the group to the function in PRD — a one-property
  change, which is exactly why it ships review-flagged rather than manual.
- **Datasources are replaced, not migrated**: the .prpt points at a JNDI name
  on the Pentaho Server. Create the connection there first; report SQL with
  Crystal parameter tokens (`{?Param}`) must be re-expressed as `${Param}`.
- **Validate the SQL against the real target before opening PRD**: the
  schema agent `EXPLAIN`s every report query against the live JNDI database
  (`pentaho-migrate report-sql`, or automatically on the Inspect page).
  Source-database column names, alias mistakes, and dialect differences
  surface in seconds instead of as blank reports in PRD — and the grounded
  chat can propose the corrected join from the introspected schema.
- **Analyzer is a re-platform, not a conversion** — use extracted SQL as
  requirements for a Mondrian model when the report is really an analysis.

## 10. Improve the tool as you go

- Every construct you convert by hand is a candidate rule or validated translation
  example. Confirmed conversions compound the tool's accuracy — that's the data moat.

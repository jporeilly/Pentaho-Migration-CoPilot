# ETL Migration Best Practices

Field-tested guidance for PowerCenter → PDI migrations, baked into how Migration
Copilot works. Read this before your first real conversion.

## 1. Inventory before you migrate

- Export **everything** first and run `pdi-migrate gaps` across the whole folder — the
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

## 9. Improve the tool as you go

- Every construct you convert by hand is a candidate rule or validated translation
  example. Confirmed conversions compound the tool's accuracy — that's the data moat.

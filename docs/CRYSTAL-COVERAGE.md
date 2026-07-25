# Crystal Reports → Pentaho Report Designer: feature coverage

What the Copilot migrates, what it becomes in PRD, and **how** it is
converted. Three methods, in order of preference (the product's design
principle — deterministic where accuracy is non-negotiable, AI only where
semantic judgment is required):

- **Deterministic** — rule-based, repeatable, no AI involved. `auto` needs
  no review; `auto → review` means the mapping is mechanical but a human
  glance is warranted (the note says why).
- **✨ LLM-assisted** — only what rules cannot prove is sent to the local
  LLM; every result is flagged `review` with the model's self-reported
  confidence shown. Never silently applied.
- **Manual (flagged)** — no faithful equivalent; converted as an explicit
  TODO placeholder or review note. The tool never guesses.

## Structure & layout — deterministic

| Crystal feature | Report Designer equivalent | Method |
| --- | --- | --- |
| Report/Page/Group/Detail bands | The same banded model (report-header, group bands, itemband, page-footer) | Deterministic |
| PageHeader on page 1 *below* the report header | Repeating **details-header** (PRD's physical page-header always tops the page) | Deterministic |
| Groups (incl. nested) | Relational groups (nested via sub-group-body), named after their column so functions reset correctly | Deterministic |
| Group sort direction | `ORDER BY ... [DESC]` in the generated query | Deterministic |
| Record sort fields | `ORDER BY` after the group columns | Deterministic |
| Element geometry (twips) | Points, position-faithful | Deterministic |
| Fonts, colors, borders, alignment, band/element backgrounds | text/content/border styles | Deterministic |
| Per-field number & date format strings | `format-string` on number/date fields (needs the forked extractor) | Deterministic |
| Object/section static suppression | `visible="false"` / band excluded | Deterministic |
| **Conditional formatting** (font color, background) | **Style expressions** (`paint`, `background-color`) with the condition translated | Deterministic → review |
| **Conditional suppression** (object & section) | **`visible` style expression** (`=NOT(condition)`) on the element/band | Deterministic → review |
| Page size, orientation, margins | page-definition | Deterministic |
| Embedded images (logo etc.) | Embedded bundle resource | Deterministic (needs image bytes in the dump) |
| Charts (bar, line, area, pie, doughnut) | Legacy-chart element + dataset collector + JFreeChart expression | Deterministic → review (verify aggregation) |
| Special fields (page N of M, print date) | PageOfPagesFunction / report.date message fields | Deterministic |

## Data & queries — deterministic

| Crystal feature | Report Designer equivalent | Method |
| --- | --- | --- |
| SQL Command objects | Query passed through verbatim; datasource replaced by a named JNDI connection | Deterministic |
| Linked tables (no SQL in the report) | SELECT generated from the columns the layout uses, with `ORDER BY` for groups/sorts (⚠ verify joins) | Deterministic → review |
| Record selection formula | Folded into the SQL `WHERE` (alias-aware for `{Command.X}` refs) — converted prompts filter live | Deterministic |
| Parameters (prompts) | PRD parameters; static pick-lists → list-parameters; multi-value → `IN (${p})` | Deterministic |
| Summary fields (Sum, Count, Avg, Max, Min, DistinctCount) | Item*/CountDistinct report functions, group-scoped | Deterministic |

## Formulas

| Crystal feature | Report Designer equivalent | Method |
| --- | --- | --- |
| Formula language (If/Then/Else, operators, ~40 function mappings, string `+`→`&` by field type) | OpenFormula | Deterministic (`auto`, or `review` when a mapping has a caveat) |
| `Select Case` (incl. multi-value branches, `a To b` ranges, `Is <op>` tests) | Nested `IF(...)` / `OR(...)` / `AND(...)` | Deterministic → review |
| `x in a to b` range test | `AND(x >= a; x <= b)` | Deterministic |
| Running-total variable idiom (`x := x + {F}`) | **Generated `ItemSumFunction`/`ItemCountFunction`** wired to referencing elements | Deterministic → review |
| Whole-formula aggregates (`Sum({F}, {G})` …) | Generated `Total*` report functions | Deterministic → review |
| Single-assignment local variable (readability alias) | Inlined into the expression | Deterministic → review |
| Everything else rules cannot prove (multi-variable state, unusual functions) | OpenFormula proposal with a color-coded **confidence chip** (high/medium/low) | ✨ LLM-assisted → review |
| Untranslatable even by the LLM | Original preserved + concrete rebuild advice (e.g. "use ItemSumFunction") | Manual (flagged) |

## Honestly manual — flagged, never guessed

| Crystal feature | What you get |
| --- | --- |
| Subreports | Red TODO placeholder at the exact position + conversion-report entry |
| Cross-tabs | TODO placeholder (rebuild as a PRD crosstab) |
| Arrays, loops, multi-variable formula state | Original text preserved, `manual` status, LLM advice |
| Group Sort Expert / Top N (groups ordered by a summary) | Review note — order in the query or rebuild with PRD group sorting |
| StdDev / Median / other summaries with no PRD function | Review note + TODO placeholder for referencing elements |
| Dynamic / cascading parameter pick-lists | Textbox parameter + note (rebuild as query-backed parameters) |
| `crNoColor` / `DefaultAttribute` conditional branches | Condition kept as a note (means "keep the static value") |

## Proof, not promises

Every conversion can be verified mechanically:

- **Engine round-trip** (`--validate`): the .prpt loads in the real Pentaho
  Reporting engine.
- **Layout QA agent** (`report-qa`): geometry lint + optional rendered-PDF
  label verification.
- **Schema agent**: the SQL is `EXPLAIN`ed against the live JNDI target;
  the grounded chat proposes fixes as reviewable diffs.
- **Output parity** (`report-parity`): the rendered report's numbers are
  diffed against the customer's Crystal export — PASS / NEAR / FAIL.
- **Batch triage** (`report-triage`): READY / REVIEW / BLOCKED verdict per
  report across a whole corpus.

Live demo set: `samples/cr_demo/` — seven CSCU reports of increasing
complexity, every one converting AND rendering against the live CSCU
database.

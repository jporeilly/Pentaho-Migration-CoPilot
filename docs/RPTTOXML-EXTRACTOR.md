# Improving the Crystal extractor (RptToXml)

The Crystal pipeline consumes an **RptToXml dump** — the XML the
[ajryan/RptToXml](https://github.com/ajryan/RptToXml) tool produces from a
`.rpt` via the SAP Crystal Reports .NET SDK. Everything downstream (parser,
formula translation, .prpt writer, live render) is proven. The remaining
fidelity ceiling is the **extractor**, not our converter.

## What stock RptToXml 1.1.7 does *not* export

Measured against the 150-report real corpus this session:

| Gap | Evidence | Impact |
|---|---|---|
| **Per-field number/date/currency format** (decimal places, currency symbol, thousands separator, negative style, date pattern) | FieldObjects carry only `<ObjectFormat>` (alignment/suppress/can-grow); no `NumericFieldFormat`/`DateFieldFormat` | **Resolved by the fork** (see below), down to date part order and separators — detail rows now match the original character for character. Without the fork, type-based defaults, and a `$#,##0.00` vs `#,##0.000` mismatch is visible to customers |
| **Embedded image bytes** | `<PictureObject>` has position/size only; no raster (SDK can't read `PictureData` — see below) | Solved converter-side: `report-images` carves the raster from the .rpt binary |
| **Group sort direction / specified order** | `<Group>` has only `ConditionField` | Direction is recovered from the `SortField` list and becomes `ORDER BY ... DESC`; Crystal's *specified order* (a hand-picked group sequence) has no PRD equivalent and stays an honest note |
| **Cross-platform / no-license extraction** | .NET Framework tool; needs the SAP Crystal runtime MSI (Windows only) | Extraction is a Windows + SAP-runtime step |

The Crystal SDK **has** all of this — RptToXml simply does not walk it. That
makes a **focused fork the pragmatic fix**, not a rewrite.

## Options considered

- **A. Fork RptToXml and export the missing properties (recommended).**
  Smallest change; reuses the SDK traversal RptToXml already does; our parser
  already reads the richer elements (below), so the fork is the only new work.
- **B. Build a bespoke `.rpt → JSON` extractor** against the SDK, emitting our
  IR directly. Cleaner long-term, but reinvents SDK traversal and is more work
  for the same near-term fidelity.
- **C. Parse the `.rpt` binary directly** (OLE2 compound doc). Cross-platform
  and license-free, but the format is proprietary and undocumented — very high
  effort, fragile. Not recommended.

## The fork (Option A) — exact changes

RptToXml's `RptDefinitionWriter.cs` walks the SDK object model. Add these
emissions (the XML shapes our parser **already reads today**):

**1. Field format string** — on each `FieldObject`, from
`FieldObject.FieldFormat`:

```xml
<FieldObject ...>
  <FieldFormat FormatString="$ #,##0.00;($ #,##0.00)"/>
</FieldObject>
```

Build the PRD pattern from `NumericFieldFormat` (`DecimalPlaces`,
`CurrencySymbolFormat`, `EnableUseLeadingZero`, `RoundingFormat`,
`NegativeFormat`) and `DateFieldFormat` / `DateTimeFieldFormat`
(`.FormatString`). → carried into `number-field` / `date-field`
`core:format-string`.

**2. Embedded image** — on each `PictureObject`, base64 of the report's
embedded resource:

```xml
<PictureObject ...><ImageData>iVBORw0KGgo...</ImageData></PictureObject>
```

→ bundled as `resources/imageN.png` with the correct manifest media type.

**3. Group sort** — on each `<Group>`, `SortDirection` from the
`DataDefController` sort model. → PRD group sort ascending/descending.

**4. Credential redaction (optional flag)** — blank
`ConnectionInfo/@UserName|@Password` at export so dumps are shareable without a
post-hoc scrub.

## Converter-side readiness (done)

Our parser and writer already read/emit all of the above when present, so the
fork's output lands with **no converter change**:

- Colours / borders / backgrounds — `<Color/BackgroundColor/BorderColor A R G B>`, `<Border ...LineStyle>` (shipped).
- Embedded image — `<PictureObject><ImageData>base64</ImageData>` (shipped).
- **Field format string** — `<FieldFormat FormatString=".."/>` or
  `<NumericFieldFormat/DateFieldFormat FormatString=".."/>` →
  `Element.format_string`, used over the type default (this release).
- Rich parameters, object suppress/can-grow (shipped).

So the improvement is **isolated to the C# fork**; the moment it emits these
elements, fidelity improves end-to-end.

## Status: the fork is BUILT and shipped

Source lives in `tools/RptToXml-fork/` (patched from upstream, license
preserved); `build.ps1` compiles it with Roslyn csc (VS Build Tools) directly
against the machine .NET Framework + the Crystal assemblies in
`tools/RptToXml/` — no MSBuild project or targeting packs needed. The output
`RptToXmlFork.exe` is preferred automatically by `extract-rpt.ps1` and
`report-env`.

What the fork adds over stock 1.1.7:

- **`<FieldFormat><NumericFieldFormat .../><DateFieldFormat .../>`** per
  FieldObject, with raw Crystal properties *and* a computed PRD-ready
  `FormatString` (`#,##0.00;-#,##0.00`, `MM/dd/yy`, …). Verified against real
  corpus reports; the converter resolves the right candidate by field type
  (formula fields use their declared result type) and carries it into the
  .prpt.
- **`RPTTOXML_REDACT=1`** blanks `ConnectionInfo` UserName/Password at
  extraction — dumps are clean at the source (extract-rpt.ps1 sets it).

**Embedded image bytes — RESOLVED, but not through the SDK.** Investigated
(2026-07-25): the RAS model *declares* `ISCRPictureObject.PictureData`
(`ByteArray`), but it **returns null in the embedded in-proc RAS** the free
runtime uses — verified with typed access across corpus reports (the same
class of truncation as cross-tab grids, whose accessors are literal
`reserved0-9` slots). Render-based harvesting (HTML export) needs the
report's live database, which customer .rpt files rarely reach. The working
approach is converter-side instead of fork-side: `pentaho-migrate
report-images <dump> <rpt>` **carves** PNG/JPEG/DIB blobs straight out of
the .rpt binary (signature scan, every candidate decode-proven with Pillow,
DIBs converted to PNG), matches them to the dump's `PictureObject`s by
aspect ratio, and injects `<ImageData Carved="true">base64</ImageData>` —
which the parser/writer already consume. `extract-rpt.ps1` runs it
automatically after each extraction. Result on the corpus: **83 images
recovered across all 44 image-bearing reports, zero misses**; each carries
a verify note through conversion.

**Currency symbol text — RESOLVED (2026-07-25):** unlike PictureData, the
RAS `NumericFieldFormat.CurrencySymbol` string IS populated in the embedded
RAS. The fork reads it per FieldObject and bakes the real symbol into the
computed `FormatString` ("$" only as the enabled-but-unnamed fallback), plus
emits `CurrencySymbol`/`CurrencyPosition` attributes.

**Date and number format PARTS — RESOLVED (2026-07-28):** the computed
`FormatString` used to assume `MM/dd/yy` ordering and default separators,
which is wrong for any report not saved in a US locale. The fork now reads
the RAS `DateFieldFormat.DateOrder` plus both separators and orders the parts
from them, and reads `NumericFieldFormat.ThousandsSeparator` and
`CurrencyPosition` so the symbol abuts the number the way Crystal prints it.
A grouped format with zero decimal places drops the grouping, matching
Crystal's own rendering. With this, the demo statement's detail row is
**character-identical** to the original (`2002/04/3 | 2886 | 5503 |
2002/05/3 | $43.50`).

Two converter-side fixes ride with it, both in `rpt_parser`: Crystal writes
value types as `crFieldValueTypeStringField`, and the un-normalized prefix
meant **no** database field ever matched the date/numeric type sets, so every
date rendered ISO and every amount unformatted; and a currency format is only
synthesized when a symbol is actually in play, because Crystal stamps
`DecimalPlaces="2"` on every field including invoice numbers.

**Running totals — RESOLVED (2026-07-25):** the ENGINE
`DataDefinition.RunningTotalFields` walk loses the reset group (rtf.Group is
null even for OnChangeOfGroup). The fork now ALSO emits RAS-side
`<RunningTotalFieldDefinition>` entries carrying `ResetCondition` (the group
field's FormulaForm); the converter dedupes by Name preferring reset-aware
entries and maps plain running totals to group-scoped Item* functions.

**Cross-tab grid definitions — RESOLVED (2026-07-25), outside the SDK:**
sealed behind reserved COM slots in the SAP model, so recovered from the
binary with rpt-rs instead — see the section below and
`report-crosstabs` in CRYSTAL-COVERAGE.md.

**Evaluated alternative — rpt-rs (2026-07-25):**
[MrSrsen/rpt-rs](https://github.com/MrSrsen/rpt-rs) (MPL-2.0) is a pure-Rust
.rpt reader/renderer with no SAP runtime: `rpt xml-dump` emits
RptToXml-compatible XML and the codebase parses **cross-tab row/column
dimensions and measures from the binary** — exactly what the SAP SDK seals
behind reserved slots.

*First evaluation (v0.2.0, release binary + from-source build) concluded
"broken on Windows, parked". That conclusion was **wrong** — the cause is a
one-line, Windows-only defect, and the tool works once it is fixed.*

**Root cause (confirmed).** `StreamId::classify`
(`crates/rpt/src/container/stream_id.rs`) splits the OLE entry path and
filters out the root component with `s != "/"`. On Windows the root
component stringifies as `\`, not `/`, so it survives the filter; every
stream then has two components, takes the "nested entry" branch, and is
returned as `Other("\\/Contents")` instead of `StreamId::Contents`. Since
only `Contents` is marked `is_tslv()`, nothing is ever decoded → 0 records,
blank renders. Verified independently: `Path::new("/Contents").components()`
yields `["\\", "Contents"]` on Windows, and **their own test suite fails
7 of 8 integration tests on Windows** before the fix.

**Fix (proven locally).** Filter the Windows root too:

```rust
.filter(|s| !s.is_empty() && s != "/" && s != "\\")
```

After that single change, on this Windows box: their fixture
`ajryan/B1Budget_M.rpt` decodes **1,475 records / 93 record types** with the
full field list; **600 of their tests pass**, with one remaining failure
that is a CRLF-vs-LF golden-file string comparison (test infrastructure,
not the library); and cross-tab records decode including
`CrossTabDimension → CrossTabDimensionGroup → CrossTabDimensionField`
with real field names (e.g. `Data.Date1`).

**Status: ADOPTED for cross-tab recovery.** The fix was submitted upstream
([MrSrsen/rpt-rs#1](https://github.com/MrSrsen/rpt-rs/pull/1)) with the
repro and a regression test. Locally, `tools/rpt-rs-src` also carries a
second change that teaches `xml-dump` to emit the decoded grid as
`<CrossTabDefinition>` (`crates/rpt-cli/src/export/objects.rs` —
the model already decoded `columns`/`rows`/`measures`, they were simply
marked "not exported").

`pentaho-migrate report-crosstabs <dump> [rpt]` shells out to that binary,
lifts the definitions and injects them into the RptToXml dump — the ordinary
conversion path then produces a live PRD crosstab. See
`src/pentaho_migration/reports/rpt_crosstabs.py`. The tool is located via
`RPT_RS_PATH`, `tools/rpt-rs/rpt[.exe]`, the cargo build output, or `PATH`;
when it is missing, cross-tabs keep their hand-add TODO exactly as before —
nothing else in the pipeline depends on it.

**Corpus result: 12 cross-tabs across 10 reports recovered**, all converting
to live crosstabs (previously all were TODOs). The SAP-based fork remains
the default extractor for everything else; rpt-rs is used only for the
records the SDK refuses to expose. Evaluation/build trees live untracked
under `tools/rpt-rs*`.

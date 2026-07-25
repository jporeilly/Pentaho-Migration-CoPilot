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
| **Per-field number/date/currency format** (decimal places, currency symbol, thousands separator, negative style, date pattern) | FieldObjects carry only `<ObjectFormat>` (alignment/suppress/can-grow); no `NumericFieldFormat`/`DateFieldFormat` | We fall back to sensible type-based defaults; a `$#,##0.00` vs `#,##0.000` mismatch is visible to customers |
| **Embedded image bytes** | `<PictureObject>` has position/size only; no raster (SDK can't read `PictureData` — see below) | Solved converter-side: `report-images` carves the raster from the .rpt binary |
| **Group sort direction / specified order** | `<Group>` has only `ConditionField` | Group ordering may differ from the original |
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

Still open (smaller): currency symbol *text*
(engine exposes only the No/Fixed/FloatingSymbol enum; "$" assumed when
enabled), and cross-tab grid definitions (SDK-sealed — hand-add
`<CrossTabDefinition>`, see CRYSTAL-COVERAGE.md).

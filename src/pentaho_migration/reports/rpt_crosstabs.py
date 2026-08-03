"""Recover cross-tab grid definitions that the SAP SDK will not export.

The free SAP .NET SDK seals a cross-tab's rows/columns/measures behind
reserved COM slots (see docs/RPTTOXML-EXTRACTOR.md), so RptToXml dumps carry
the CrossTabObject's geometry and nothing else — which is why a cross-tab
otherwise needs a hand-written <CrossTabDefinition> block before it converts.

rpt-rs (MPL-2.0, https://github.com/MrSrsen/rpt-rs) decodes those records
straight from the .rpt binary. This adapter shells out to its
`rpt json-dump` (v0.4.0+; it replaced the retired `xml-dump`), reads the
grid out of the JSON model, and injects an equivalent <CrossTabDefinition>
into the matching CrossTabObject of an existing RptToXml dump — so the
ordinary conversion path picks it up with no further change.

In the JSON model a cross-tab's `rows`/`columns` list its dimension levels
(grand-total levels carry an empty `field_ref` and are structural, not
user-chosen groupings), while the data-cell measures are the report's
pre-layout Summary field definitions — shared across the report, exactly
the list the retired xml-dump serialised per cross-tab as <SummaryFields>.

Field references are normalised on the way in: rpt-rs emits bare
`Table.Field` / `@Formula`, our parser expects the RptToXml `{...}` form.

Everything here is best-effort and honest: no rpt binary, an unreadable
report, or a cross-tab rpt-rs cannot decode simply leaves the dump alone,
and the report keeps its existing TODO.
"""

import json
import shutil
import subprocess

from pentaho_migration.reports.proc import run_nice
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[3]

# Where we look for the rpt-rs CLI, in order. RPT_RS_PATH overrides
# everything. Needs v0.4.0+ (`json-dump`; `saved` emits real, un-scaled
# numeric values) — an older build answers with a usage error and recovery
# honestly reports nothing.
_CANDIDATES = (
    REPO_ROOT / "tools" / "rpt-rs" / "rpt.exe",
    REPO_ROOT / "tools" / "rpt-rs" / "rpt",
)

TIMEOUT = 120.0


def find_rpt_rs() -> Path | None:
    """The rpt-rs CLI, or None when it is not installed."""
    import os

    override = os.environ.get("RPT_RS_PATH")
    if override and Path(override).is_file():
        return Path(override)
    for candidate in _CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("rpt")
    return Path(found) if found else None


def _normalise_ref(ref: str) -> str:
    """`Data.Date1` -> `{Data.Date1}`; `@Total` -> `{@Total}`. Already-braced
    references pass through untouched."""
    ref = (ref or "").strip()
    if not ref:
        return ""
    if ref.startswith("{") and ref.endswith("}"):
        return ref
    return "{" + ref + "}"


def _report_nodes(model: dict):
    """The report model plus every nested subreport model, in document order
    (a subreport entry wraps its model under `report`)."""
    yield model
    for sub in model.get("subreports") or []:
        inner = (sub or {}).get("report")
        if isinstance(inner, dict):
            yield from _report_nodes(inner)


def _summary_measures(report: dict) -> list:
    """[(field ref, operation)] from the report's Summary field definitions.

    These are the pre-layout summary records — the same report-level list the
    retired xml-dump serialised as every cross-tab's <SummaryFields> (the
    binary does not tie a measure to one grid; running totals live under
    their own kind and stay excluded, as before)."""
    measures = []
    for fd in (report.get("data_definition") or {}).get("field_definitions") or []:
        kind = fd.get("kind")
        if not isinstance(kind, dict) or "Summary" not in kind:
            continue
        summary = kind["Summary"] or {}
        field = str(summary.get("summarized_field") or "")
        operation = summary.get("operation")
        if field:
            # a parameterized operation serialises as {name: parameter}
            if isinstance(operation, dict) and operation:
                operation = next(iter(operation))
            measures.append((field, str(operation or "Sum")))
    return measures


def _crosstab_objects(report: dict):
    """Every (object, CrossTab payload) placed in the report's layout."""
    for area in (report.get("report_definition") or {}).get("areas") or []:
        for section in area.get("sections") or []:
            for obj in section.get("objects") or []:
                kind = obj.get("kind")
                if isinstance(kind, dict) and "CrossTab" in kind:
                    yield obj, kind["CrossTab"] or {}


def _axis_refs(ct: dict, axis: str) -> list:
    """The user-chosen dimension levels of one axis, in order. Grand-total
    levels carry an empty field_ref and are skipped — structural, not
    groupings."""
    return [d["field_ref"] for d in ct.get(axis) or [] if d.get("field_ref")]


def extract_definitions(rpt_path: Path, exe: Path | None = None) -> dict:
    """{crosstab object name: <CrossTabDefinition> Element} decoded from the
    .rpt binary by rpt-rs. Empty when the tool is unavailable or the report
    yields nothing — never raises for an unreadable report."""
    exe = exe or find_rpt_rs()
    if exe is None or not rpt_path.is_file():
        return {}
    try:
        proc = run_nice(
            [str(exe), "json-dump", str(rpt_path)],
            capture_output=True, timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0 or not proc.stdout:
        return {}
    try:
        doc = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}

    out = {}
    for report in _report_nodes(doc.get("model") or {}):
        measures = _summary_measures(report)
        for obj, ct in _crosstab_objects(report):
            rows = _axis_refs(ct, "rows")
            cols = _axis_refs(ct, "columns")
            if not (rows and cols and measures):
                continue  # a partial grid is not usable — leave the TODO in place
            definition = ET.Element("CrossTabDefinition")
            for tag, refs in (("RowFields", rows), ("ColumnFields", cols)):
                axis = ET.SubElement(definition, tag)
                for ref in refs:
                    ET.SubElement(axis, "Field", FieldName=_normalise_ref(ref))
            sums = ET.SubElement(definition, "SummaryFields")
            for field, operation in measures:
                ET.SubElement(sums, "Field", FieldName=_normalise_ref(field),
                              Operation=operation)
            out[obj.get("name", "")] = definition
    return out


def enrich_dump(dump_path: Path, rpt_path: Path, out_path: Path | None = None) -> int:
    """Inject recovered <CrossTabDefinition> blocks into an RptToXml dump
    (in place unless out_path is given). CrossTabObjects that already carry a
    definition — hand-written or previously recovered — are left untouched.
    Returns the number of cross-tabs enriched."""
    definitions = extract_definitions(Path(rpt_path))
    if not definitions:
        return 0
    tree = ET.parse(dump_path)
    targets = [el for el in tree.getroot().iter("CrossTabObject")
               if el.find("CrossTabDefinition") is None]
    if not targets:
        return 0

    injected = 0
    unmatched = [d for name, d in definitions.items()
                 if name not in {t.get("Name", "") for t in targets}]
    for target in targets:
        definition = definitions.get(target.get("Name", ""))
        if definition is None:
            # names disagree between extractors: fall back to a positional
            # match only when it is unambiguous (one cross-tab, one definition)
            if len(targets) == 1 and len(definitions) == 1:
                definition = next(iter(definitions.values()))
            elif len(targets) == 1 and len(unmatched) == 1:
                definition = unmatched[0]
            else:
                continue
        recovered = ET.fromstring(ET.tostring(definition))
        recovered.set("Recovered", "rpt-rs")  # parser adds a verify note
        target.append(recovered)
        injected += 1
    if injected:
        tree.write(out_path or dump_path, encoding="utf-8", xml_declaration=True)
    return injected


def describe_availability() -> str:
    """One line for the CLI/preflight: is cross-tab recovery possible here?"""
    exe = find_rpt_rs()
    if exe is None:
        return ("rpt-rs not found - cross-tab definitions cannot be recovered "
                "automatically (add tools/rpt-rs/rpt[.exe] or set RPT_RS_PATH). "
                "Hand-add <CrossTabDefinition> instead.")
    return f"rpt-rs found at {exe} - cross-tab definitions can be recovered from .rpt binaries."

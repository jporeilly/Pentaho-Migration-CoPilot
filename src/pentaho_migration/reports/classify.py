"""Classify a Crystal corpus by migration feature, so real-world reports can
be picked for demos by what they demonstrate.

Each report is scanned once (through the normal load pipeline) and tagged
with every feature it exhibits; `classify_corpus` then materializes a
by-feature folder tree (a multi-feature report is copied into every matching
folder) plus a generated README index.
"""

import re
import shutil
from pathlib import Path

from pentaho_migration.reports import load_report_model

# feature key -> (folder name, human description)
FEATURES = {
    "subreports": ("sub-reports", "nested subreport definitions (converted to PRD sub-reports)"),
    "charts": ("charts", "chart objects (converted to PRD legacy charts)"),
    "crosstabs": ("cross-tabs", "cross-tab objects (honest TODO placeholders)"),
    "parameters": ("parameters", "prompted parameters"),
    "multi-value-params": ("multi-value-params", "multi-select prompts (IN-list folding)"),
    "record-selection": ("record-selection", "record selection formulas (SQL WHERE folding)"),
    "groups": ("groups", "grouped reports"),
    "nested-groups": ("nested-groups", "two or more nested groups"),
    "summaries": ("summaries", "summary fields (report functions)"),
    "running-totals": ("running-totals", "running-total idiom rewritten as report functions"),
    "select-case": ("select-case", "Select Case formulas (nested IF conversion)"),
    "conditional-formatting": ("conditional-formatting", "conditional format/suppress formulas (style expressions)"),
    "sort-directions": ("sort-directions", "explicit record/group sort fields"),
    "images": ("images", "picture objects"),
    "manual-formulas": ("manual-formulas", "formulas needing the LLM or a human"),
    "linked-tables": ("linked-tables", "no SQL command - the query is generated from the layout"),
    "sql-commands": ("sql-commands", "verbatim SQL command objects"),
}


def detect_features(model) -> list[str]:
    found = set()
    elements = [el for s in model.sections for el in s.elements]
    if model.subreports:
        found.add("subreports")
    if any(el.kind == "chart" for el in elements):
        found.add("charts")
    if any("CrossTab" in (el.text or "") for el in elements if el.kind == "unknown"):
        found.add("crosstabs")
    if model.parameters:
        found.add("parameters")
    if any(p.multi_value for p in model.parameters):
        found.add("multi-value-params")
    if model.record_selection:
        found.add("record-selection")
    if model.groups:
        found.add("groups")
    if len(model.groups) >= 2:
        found.add("nested-groups")
    if model.summaries:
        found.add("summaries")
    if any(f.rewrite_class for f in model.formulas.values()):
        found.add("running-totals")
    if any(re.match(r"(?i)\s*select\b", f.text or "") for f in model.formulas.values()):
        found.add("select-case")
    if (any(el.condition_formulas or el.style_expressions for el in elements)
            or any(s.condition_formulas or s.style_expressions for s in model.sections)):
        found.add("conditional-formatting")
    if model.record_sorts or any(g.descending for g in model.groups):
        found.add("sort-directions")
    if any(el.kind == "image" for el in elements):
        found.add("images")
    if any(f.status == "manual" for f in model.formulas.values()):
        found.add("manual-formulas")
    if model.sql_generated:
        found.add("linked-tables")
    else:
        found.add("sql-commands")
    return sorted(found)


def classify_corpus(src: Path, dest: Path, progress=None):
    """Scan every dump in src, copy each into dest/<feature>/ for every
    feature it demonstrates, and write dest/README.md. Returns
    {filename: [features]}; parse failures are skipped with a note."""
    src, dest = Path(src), Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    results, failures = {}, []
    files = sorted(src.glob("*.xml"))
    for i, dump in enumerate(files):
        try:
            model = load_report_model(dump)
            results[dump.name] = detect_features(model)
            for feature in results[dump.name]:
                folder = dest / FEATURES[feature][0]
                folder.mkdir(exist_ok=True)
                shutil.copy2(dump, folder / dump.name)
        except Exception as exc:
            failures.append((dump.name, str(exc)[:80]))
        if progress:
            progress(i + 1, len(files))

    lines = ["# Crystal corpus, classified by migration feature", "",
             f"{len(results)} reports scanned from `{src.as_posix()}`. A report "
             "demonstrating several features appears in several folders - "
             "pick demo reports by the feature you want to show.", "",
             "| Folder | Feature | Reports |", "| --- | --- | --- |"]
    for key, (folder, desc) in FEATURES.items():
        count = sum(1 for feats in results.values() if key in feats)
        if count:
            lines.append(f"| `{folder}/` | {desc} | {count} |")
    lines += ["", "## Per-report features", ""]
    for name in sorted(results):
        lines.append(f"- `{name}` — {', '.join(results[name])}")
    if failures:
        lines += ["", "## Skipped (parse failures)", ""]
        lines += [f"- `{n}`: {e}" for n, e in failures]
    (dest / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results

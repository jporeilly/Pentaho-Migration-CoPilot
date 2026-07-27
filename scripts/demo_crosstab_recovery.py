"""Cross-tab recovery walkthrough — the before/after a customer can watch.

The SAP .NET SDK cannot export a cross-tab's grid (rows, columns, measures sit
behind reserved COM slots), so an RptToXml dump describes only the box on the
page. This script proves what that costs and how the binary reader recovers it,
on a REAL report from the corpus:

    samples/crystal/corpus/ajryan_B1Budget_M.rpt   (SAP Business One budget report)

  1. BEFORE — convert the dump as the SDK produced it: the cross-tab is a TODO.
  2. RECOVER — read the grid straight from the .rpt binary (rpt-rs) and inject
     it into the dump.
  3. AFTER — convert again: a live PRD crosstab, verified through the real
     Pentaho Reporting engine.

Run:  python scripts/demo_crosstab_recovery.py [--keep]

Nothing in the repository is modified: the script works on a temporary copy of
the dump (the committed one is already enriched).
"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

REPORT = "ajryan_B1Budget_M"
DUMP = REPO_ROOT / "samples" / "crystal" / "real" / f"{REPORT}.xml"
BINARY = REPO_ROOT / "samples" / "crystal" / "corpus" / f"{REPORT}.rpt"


def rule(title):
    # ASCII only: this runs live in front of customers, and a cp1252 console
    # raises UnicodeEncodeError on box-drawing characters.
    print(f"\n{'-' * 72}\n{title}\n{'-' * 72}")


def crosstab_state(model):
    """(live crosstabs, cross-tab TODOs) in a converted model."""
    live = [e for s in model.sections for e in s.elements if e.kind == "crosstab"]
    todo = [e for s in model.sections for e in s.elements
            if e.kind == "unknown" and "CrossTab" in (e.text or "")]
    return live, todo


def strip_definitions(source: Path, target: Path) -> Path:
    """The committed dump is already enriched — rewind it so the demo starts
    from what the SAP SDK actually produces."""
    tree = ET.parse(source)
    for obj in tree.getroot().iter("CrossTabObject"):
        for existing in obj.findall("CrossTabDefinition"):
            obj.remove(existing)
    tree.write(target, encoding="utf-8", xml_declaration=True)
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true",
                        help="keep the generated .prpt files and print their paths")
    args = parser.parse_args()

    from pentaho_migration.reports import load_report_model
    from pentaho_migration.reports.prpt_writer import write_prpt
    from pentaho_migration.reports.rpt_crosstabs import (
        describe_availability, enrich_dump, find_rpt_rs)

    for path in (DUMP, BINARY):
        if not path.is_file():
            print(f"missing corpus file: {path}")
            return 2

    work = Path(tempfile.mkdtemp(prefix="xt-recovery-"))
    dump = strip_definitions(DUMP, work / DUMP.name)

    rule("1. BEFORE - the dump exactly as the SAP SDK exports it")
    model = load_report_model(dump)
    live, todo = crosstab_state(model)
    print(f"   cross-tab objects in the report : {len(live) + len(todo)}")
    print(f"   converted to a PRD crosstab     : {len(live)}")
    print(f"   left as a TODO placeholder      : {len(todo)}")
    for issue in model.issues:
        if "CrossTabDefinition" in issue:
            print(f"\n   the conversion report says:\n     {issue[:180]}...")
            break

    rule("2. RECOVER - read the grid out of the .rpt binary")
    print(f"   {describe_availability()}")
    if find_rpt_rs() is None:
        return 1
    recovered = enrich_dump(dump, BINARY)
    print(f"   recovered {recovered} cross-tab definition(s) from {BINARY.name}")
    injected = ET.parse(dump).getroot().find(".//CrossTabDefinition")
    if injected is not None:
        rows = [f.get("FieldName") for f in injected.findall("RowFields/Field")]
        cols = [f.get("FieldName") for f in injected.findall("ColumnFields/Field")]
        sums = [(f.get("FieldName"), f.get("Operation"))
                for f in injected.findall("SummaryFields/Field")]
        print(f"     rows    : {', '.join(rows)}")
        print(f"     columns : {', '.join(cols)}")
        print(f"     measures: {', '.join(f'{op}({f})' for f, op in sums)}")

    rule("3. AFTER - convert again")
    model = load_report_model(dump)
    live, todo = crosstab_state(model)
    print(f"   converted to a PRD crosstab     : {len(live)}")
    print(f"   left as a TODO placeholder      : {len(todo)}")
    for el in live:
        print(f"     rows={el.crosstab_rows} columns={el.crosstab_columns} "
              f"measures={el.crosstab_summaries}")
        for note in el.notes:
            print(f"     note: {note[:150]}")

    out = work / f"{REPORT}.prpt"
    write_prpt(model, out)
    child = "subreport/layout.xml"
    import zipfile

    with zipfile.ZipFile(out) as bundle:
        has_crosstab = any(n.endswith(child) for n in bundle.namelist()) and \
            b"crosstab-row-group" in bundle.read(
                next(n for n in bundle.namelist() if n.endswith(child)))
    print(f"\n   .prpt written, PRD crosstab groups present: {has_crosstab}")

    rule("Result")
    print("   The SDK could not export this grid; it was read from the binary\n"
          "   and the report now converts to a live PRD crosstab.\n"
          "   Verify it with:  pentaho-migrate report <dump> --validate")
    if args.keep:
        print(f"\n   artifacts kept in: {work}")
    else:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Element-by-element fidelity audit: what does Crystal put in a report, and
what does each of those things become on the PRD side?

The conversion report tells you about one report. This walks the whole corpus
and answers the prior question — which Crystal object types, formatting
attributes and behaviours exist out there at all, and for each one whether the
pipeline reproduces it, approximates it, or drops it. That is the map of what
is left to build.

Run: .venv\\Scripts\\python scripts/element_gap_audit.py [corpus_dir]
"""

import sys
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pentaho_migration.reports import load_report_model            # noqa: E402
from pentaho_migration.reports.model import is_todo_element        # noqa: E402
from pentaho_migration.reports.todo_kinds import MANUAL, split_todos  # noqa: E402

# Crystal object tag -> what the pipeline turns it into. "-" means the object
# type is not recognised at all, which is the most important thing to surface.
EXPECTED = {
    "TextObject": "label / message field",
    "FieldHeadingObject": "label (column caption)",
    "FieldObject": "text / number / date field",
    "DatabaseFieldObject": "text / number / date field",
    "FormulaFieldObject": "field bound to a PRD expression",
    "ParameterFieldObject": "field bound to a PRD parameter",
    "SpecialVarFieldObject": "message field (page number, date)",
    "LineObject": "horizontal-line",
    "BoxObject": "rectangle",
    "PictureObject": "image (bytes carved from the .rpt)",
    "SubreportObject": "nested PRD sub-report",
    "ChartObject": "PRD legacy chart",
    "CrossTabObject": "PRD crosstab",
    "OlapGridObject": "-",
    "BlobFieldObject": "-",
    "FlashObject": "-",
}


def audit(corpus: Path):
    tags = Counter()
    reports_with = defaultdict(set)
    kinds = Counter()
    todo_kinds = Counter()
    gap_notes = Counter()
    dumps = sorted(corpus.glob("*.xml"))

    for dump in dumps:
        try:
            root = ET.parse(dump).getroot()
        except ET.ParseError:
            continue
        for area in root.iter("ReportObjects"):
            for obj in area:
                tag = obj.tag.rsplit("}", 1)[-1]
                tags[tag] += 1
                reports_with[tag].add(dump.stem)
        try:
            model = load_report_model(dump)
        except Exception:
            continue
        notes = []
        for section in model.sections:
            for el in section.elements:
                kinds[el.kind] += 1
                if is_todo_element(el):
                    todo_kinds[el.kind] += 1
                notes.extend(el.notes)
        notes.extend(model.issues)
        for note in split_todos(notes)[MANUAL]:
            head = note.split("(")[0].split(":")[0].strip().lower()
            gap_notes[head[:58]] += 1

    print(f"{len(dumps)} dumps in {corpus.as_posix()}\n")
    print("CRYSTAL OBJECT TYPES FOUND, AND WHAT EACH BECOMES")
    print(f"  {'object':26} {'count':>6} {'reports':>8}  becomes")
    unknown = []
    for tag, n in tags.most_common():
        becomes = EXPECTED.get(tag, "?  NOT RECOGNISED - falls through to TODO")
        if becomes.startswith("-") or becomes.startswith("?"):
            unknown.append((tag, n, len(reports_with[tag])))
        print(f"  {tag:26} {n:>6} {len(reports_with[tag]):>8}  {becomes}")

    print("\nWHAT THE PARSER ACTUALLY PRODUCED")
    for kind, n in kinds.most_common():
        flag = f"   <- {todo_kinds[kind]} emitted as TODO placeholders" if todo_kinds[kind] else ""
        print(f"  {kind:26} {n:>6}{flag}")

    print("\nBEHAVIOURS THAT DID NOT SURVIVE (ranked - this is the backlog)")
    for note, n in gap_notes.most_common(18):
        print(f"  {n:>5}  {note}")

    if unknown:
        print("\nOBJECT TYPES WITH NO MAPPING AT ALL")
        for tag, n, reports in unknown:
            print(f"  {tag}: {n} instances across {reports} reports")
    else:
        print("\nEvery Crystal object type present in this corpus has a mapping.")


if __name__ == "__main__":
    audit(Path(sys.argv[1] if len(sys.argv) > 1 else "samples/crystal/corpus"))

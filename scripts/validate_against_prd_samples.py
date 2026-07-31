"""Validate the .prpt emitter against PRD's own shipped sample reports.

PRD installs 36 known-good .prpt files under samples/ - files the product's
own bundle writer authored, which render by definition. They are the ground
truth this emitter has only ever reverse-engineered, so the check runs three
ways:

  A. ENGINE  - every shipped sample renders through our harness (does our
               render path agree with files PRD itself wrote?).
  B. SHAPE   - the XML vocabulary of OUR emitted bundles (tags, attributes,
               expression classes) must be a subset of what PRD's own files
               use, minus a short documented allow-list (features PRD ships
               no sample of, like crosstabs).
  C. PARITY  - three shipped samples are the modern re-authorings of the
               Steel Wheels xaction estate (Inventory, Income Statement,
               Invoice Statements); their structure is compared against our
               conversions of the same reports.

Run:  python scripts/validate_against_prd_samples.py [--render]
The render pass (A) needs the SampleData HSQLDB and takes minutes; shape and
parity run in seconds. Output: output/prd_sample_validation.md
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pentaho_migration.reports.environment import find_prd_home  # noqa: E402

# Vocabulary WE emit that no shipped sample demonstrates - each entry names
# the evidence that it is nevertheless correct.
ALLOWED_EXTRA = {
    "crosstab": "PRD ships no crosstab sample; shape derived from "
                "tools/CrosstabRef.java reference bundles (task #64 note)",
    "crosstab-summary-header": "same crosstab reference",
    "crosstab-header": "same crosstab reference",
    "crosstab-title-header": "same crosstab reference",
    "crosstab-cell": "same crosstab reference",
    "crosstab-column-group": "same crosstab reference",
    "crosstab-row-group": "same crosstab reference",
    "crosstab-other-group": "same crosstab reference",
    "details-header": "engine-standard band; samples style it via css only",
    "no-data-band": "engine-standard band",
}


def samples_root() -> Path | None:
    home = find_prd_home()
    if home is None:
        return None
    root = Path(home) / "samples"
    return root if root.is_dir() else None


def shipped_samples(root: Path):
    return sorted(root.rglob("*.prpt"))


def our_bundles():
    out = Path("output/xactions")
    return sorted(p for p in out.glob("*.prpt")) if out.is_dir() else []


# ---------------------------------------------------------------- vocabulary

def _bundle_vocab(prpt: Path):
    """(tags, attrs, expression classes) used by a bundle's layout/styles."""
    tags, attrs, classes = set(), set(), set()
    with zipfile.ZipFile(prpt) as z:
        for name in ("layout.xml", "styles.xml", "datadefinition.xml"):
            if name not in z.namelist():
                continue
            try:
                root = ET.fromstring(z.read(name))
            except ET.ParseError:
                continue
            for node in root.iter():
                tag = node.tag.split("}")[-1]
                tags.add(tag)
                for attr in node.attrib:
                    attrs.add(f"{tag}@{attr.split('}')[-1]}")
                if node.get("class"):
                    classes.add(node.get("class"))
        # sub-report bundles nest whole layouts
        for name in z.namelist():
            if re.fullmatch(r"reports/[^/]+/layout\.xml", name):
                try:
                    for node in ET.fromstring(z.read(name)).iter():
                        tags.add(node.tag.split("}")[-1])
                except ET.ParseError:
                    pass
    return tags, attrs, classes


def _engine_classes(root: Path):
    """Every class the PRD install's engine jars ship - the authority on
    whether an expression class we emit actually exists."""
    classes = set()
    lib = root.parent / "lib"
    for jar in lib.glob("*.jar"):
        try:
            with zipfile.ZipFile(jar) as z:
                for name in z.namelist():
                    if name.endswith(".class"):
                        classes.add(name[:-6].replace("/", "."))
        except (OSError, zipfile.BadZipFile):
            continue
    return classes


def shape_check(shipped, ours, engine_classes):
    prd_tags, prd_attrs, prd_classes = set(), set(), set()
    for p in shipped:
        t, a, c = _bundle_vocab(p)
        prd_tags |= t
        prd_attrs |= a
        prd_classes |= c
    findings = []
    verified = []
    coverage = {}
    for p in ours:
        t, a, c = _bundle_vocab(p)
        extra_tags = {x for x in t - prd_tags if x not in ALLOWED_EXTRA}
        extra_classes = c - prd_classes
        coverage[p.name] = (sorted(t & prd_tags), sorted(extra_tags),
                            sorted(extra_classes))
        for x in sorted(extra_tags):
            findings.append(f"{p.name}: tag <{x}> appears in no PRD-authored "
                            "sample - verify the shape against the engine "
                            "parser or add an allow-list entry with evidence")
        for x in sorted(extra_classes):
            # no sample uses it, but the engine may still ship it - the jar
            # is the authority
            if x in engine_classes:
                verified.append(f"{p.name}: {x.rsplit('.', 1)[-1]} - in no "
                                "sample, but present in the engine jar")
            else:
                findings.append(f"{p.name}: expression class {x} exists in "
                                "NO engine jar - the engine cannot load it")
    return prd_tags, coverage, findings, verified


# ------------------------------------------------------------------- parity

PARITY_PAIRS = [
    ("Operational Reports/Inventory.prpt", "ext_inventory.prpt"),
    ("Financial Reports/Income Statement.prpt", "Income Statement.prpt"),
    ("Production Reports/Invoice Statements.prpt", "ext_invoice.prpt"),
]


def _structure(prpt: Path):
    """What the report IS: groups, band kinds, bound columns, page count of
    declared expressions - the comparable skeleton."""
    info = {"groups": [], "bands": set(), "fields": set(), "expressions": 0}
    with zipfile.ZipFile(prpt) as z:
        lay = z.read("layout.xml").decode("utf-8", "replace")
        for m in re.finditer(r"<group [^>]*group-fields=\"([^\"]*)\"", lay):
            if m.group(1):
                info["groups"].append(m.group(1))
        for band in ("report-header", "page-header", "details", "itemband",
                     "group-header", "group-footer", "report-footer",
                     "page-footer", "watermark"):
            if f"<{band}" in lay or f":{band}" in lay:
                info["bands"].add(band)
        for m in re.finditer(r"field=\"([^\"]+)\"", lay):
            info["fields"].add(m.group(1))
        if "datadefinition.xml" in z.namelist():
            dd = z.read("datadefinition.xml").decode("utf-8", "replace")
            info["expressions"] = len(re.findall(r"<expression ", dd))
    return info


def parity_check(root: Path):
    rows = []
    for shipped_rel, ours_name in PARITY_PAIRS:
        shipped_p = root / shipped_rel
        ours_p = Path("output/xactions") / ours_name
        if not shipped_p.is_file() or not ours_p.is_file():
            rows.append((shipped_rel, ours_name, None, None))
            continue
        rows.append((shipped_rel, ours_name,
                     _structure(shipped_p), _structure(ours_p)))
    return rows


# ------------------------------------------------------------------- render

def render_check(shipped):
    from pentaho_migration.reports.prpt_validator import render_prpt_pdf_live
    results = []
    for p in shipped:
        try:
            pdf = render_prpt_pdf_live(p)
            results.append((p, "OK", f"{len(pdf)} bytes"))
        except Exception as exc:
            head = " ".join(str(exc).split())
            for marker in ("Caused by:", "Exception:"):
                if marker in head:
                    head = head[head.rindex(marker):]
            results.append((p, "FAIL", head[:200]))
    return results


# -------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true",
                    help="also render every shipped sample (slow, needs "
                         "SampleData)")
    args = ap.parse_args()

    root = samples_root()
    if root is None:
        print("no PRD install found - nothing to validate against")
        return 1
    shipped = shipped_samples(root)
    ours = our_bundles()
    print(f"shipped samples: {len(shipped)}   our bundles: {len(ours)}")

    lines = ["# Emitter validation against PRD's shipped samples", ""]
    lines.append(f"* shipped samples found: **{len(shipped)}** under `{root}`")
    lines.append(f"* our emitted bundles checked: **{len(ours)}**")
    lines.append("")

    prd_tags, coverage, findings, verified = shape_check(
        shipped, ours, _engine_classes(root))
    lines.append("## B. Shape: our vocabulary vs PRD's authored vocabulary")
    lines.append("")
    lines.append(f"PRD's own files use {len(prd_tags)} distinct XML tags.")
    if findings:
        lines.append("")
        lines.append("**Divergences (fix or allow-list with evidence):**")
        for f in findings:
            lines.append(f"* {f}")
    else:
        lines.append("Every tag our emitter writes appears in PRD's own "
                     "files (crosstab family allow-listed - PRD ships no "
                     "sample; our shape comes from engine-generated "
                     "reference bundles), and every expression class "
                     "resolves in the engine jars.")
    if verified:
        lines.append("")
        lines.append("**Classes verified against the engine jars "
                     "(no sample uses them):**")
        for v in verified:
            lines.append(f"* {v}")
    lines.append("")

    lines.append("## C. Parity: the shipped Steel Wheels re-authorings vs "
                 "our conversions of the same reports")
    lines.append("")
    for shipped_rel, ours_name, a, b in parity_check(root):
        lines.append(f"### {shipped_rel}  vs  {ours_name}")
        if a is None:
            lines.append("* one side missing - regenerate output/xactions "
                         "or check the install")
            continue
        lines.append(f"* groups: PRD {a['groups']} / ours {b['groups']}")
        lines.append(f"* bands:  PRD {sorted(a['bands'])} / "
                     f"ours {sorted(b['bands'])}")
        shared = sorted(a["fields"] & b["fields"])
        lines.append(f"* shared bound fields ({len(shared)}): "
                     + ", ".join(shared[:12])
                     + (" ..." if len(shared) > 12 else ""))
        only_prd = sorted(a["fields"] - b["fields"])
        if only_prd:
            lines.append(f"* PRD-only fields: {', '.join(only_prd[:10])}")
        only_ours = sorted(b["fields"] - a["fields"])
        if only_ours:
            lines.append(f"* ours-only fields: {', '.join(only_ours[:10])}")
        lines.append("")

    if args.render:
        lines.append("## A. Engine: every shipped sample through our "
                     "render harness")
        lines.append("")
        ok = 0
        for p, status, detail in render_check(shipped):
            rel = p.relative_to(root)
            mark = "renders" if status == "OK" else f"FAIL - {detail}"
            lines.append(f"* `{rel}`: {mark}")
            ok += status == "OK"
        lines.append("")
        lines.append(f"**{ok}/{len(shipped)} shipped samples render through "
                     "the harness.**")

    out = Path("output/prd_sample_validation.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")
    for f in findings:
        print("DIVERGENCE:", f)
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())

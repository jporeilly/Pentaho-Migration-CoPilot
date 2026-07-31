"""The emitter validated against PRD's own shipped sample reports (#64).

PRD installs 36 known-good .prpt files - the product's own bundle writer
authored them, so they are the ground truth for the XML shapes we emit.
Skipped wholesale when no PRD install is present.
"""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "validate_against_prd_samples",
    Path(__file__).resolve().parents[1]
    / "scripts" / "validate_against_prd_samples.py")
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)

ROOT = harness.samples_root()

pytestmark = pytest.mark.skipif(ROOT is None,
                                reason="no PRD install with samples/")


class TestShippedSamples:
    def test_the_install_ships_the_full_sample_set(self):
        assert len(harness.shipped_samples(ROOT)) >= 30

    def test_our_emitted_shapes_stay_inside_prd_vocabulary(self, tmp_path):
        """Every tag we emit must appear in PRD-authored files (or the
        documented crosstab allow-list), and every expression class must
        resolve in the engine jars. This is the check that caught the
        dead <value-list> parameter shape."""
        from pentaho_migration.reports.xaction_parser import build_report_model
        from pentaho_migration.reports.prpt_writer import write_prpt

        sw = Path("samples/xactions/corpus/steel-wheels-reports")
        bundles = []
        for xa in ("Inventory List.xaction", "Variance Report.xaction"):
            m = build_report_model(sw / xa)
            out = tmp_path / (Path(xa).stem + ".prpt")
            write_prpt(m, out)
            bundles.append(out)
        shipped = harness.shipped_samples(ROOT)
        _tags, _cov, findings, _verified = harness.shape_check(
            shipped, bundles, harness._engine_classes(ROOT))
        assert findings == []

    def test_parity_with_the_shipped_steel_wheels_reauthorings(self):
        """PRD's Inventory.prpt IS the modern Inventory List; our conversion
        of the original xaction must land on the same skeleton."""
        a = harness._structure(ROOT / "Operational Reports" / "Inventory.prpt")
        ours = Path("output/xactions/ext_inventory.prpt")
        if not ours.is_file():
            pytest.skip("regenerate output/xactions first")
        b = harness._structure(ours)
        assert a["groups"] == b["groups"] == ["PRODUCTLINE"]
        assert a["bands"] == b["bands"]

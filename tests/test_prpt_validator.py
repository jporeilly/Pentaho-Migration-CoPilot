"""Round-trip validation through the real Pentaho Reporting engine.

The engine tests run only where a PRD install + Java exist (this box, not
CI) — the environment/detection tests run everywhere."""

import zipfile

import pytest

from pentaho_migration.reports import load_report_model, write_prpt
from pentaho_migration.reports.environment import environment_report, find_java, find_prd_home
from pentaho_migration.reports.prpt_validator import validate_prpts, validator_available

from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "branch_transactions.xml"

needs_engine = pytest.mark.skipif(
    not validator_available(), reason="no local PRD install + Java")


def test_environment_report_shape():
    env = environment_report()
    assert set(env) >= {"prd_home", "java", "crystal_runtime", "rpttoxml",
                        "validator_ready", "extraction_ready", "hints"}
    assert isinstance(env["hints"], list)


def test_find_java_tolerates_missing_prd():
    # must not raise, whatever the machine looks like
    find_java(None)
    find_prd_home()


@needs_engine
def test_generated_bundle_loads_in_real_engine(tmp_path):
    model = load_report_model(SAMPLE, jndi="CSCU")
    out = tmp_path / "branch.prpt"
    write_prpt(model, out)
    (result,) = validate_prpts([out])
    assert result.ok, result.detail
    assert "groups=1" in result.detail
    assert "parameters=1" in result.detail
    assert "dataFactory=true" in result.detail


@needs_engine
def test_validator_catches_corrupted_bundle(tmp_path):
    model = load_report_model(SAMPLE)
    good = tmp_path / "good.prpt"
    write_prpt(model, good)
    bad = tmp_path / "bad.prpt"
    with zipfile.ZipFile(good) as zin, zipfile.ZipFile(bad, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "layout.xml":
                data = data.replace(b"</layout>", b"<unclosed>")
            zout.writestr(item, data)
    results = validate_prpts([good, bad])
    verdicts = {Path(r.path).name: r.ok for r in results}
    assert verdicts["good.prpt"] is True
    assert verdicts["bad.prpt"] is False

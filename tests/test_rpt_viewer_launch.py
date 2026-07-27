"""Opening the ORIGINAL .rpt in the local Crystal viewer.

This is the one place the app starts a desktop process from an HTTP request,
so most of these tests are about the bounds: local callers only, a fixed
executable, and paths that must resolve to a .rpt inside the allowed roots.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.reports import rpt_viewer

REPO = Path(__file__).resolve().parents[1]
# TestClient reports host "testclient" by default; be explicit about
# where the call comes from, since that is exactly what is guarded.
client = TestClient(app, client=("127.0.0.1", 12345))
remote_client = TestClient(app, client=("10.0.0.5", 51234))


class TestMatching:
    def test_extracted_dump_finds_its_binary(self):
        if not (REPO / "samples" / "crystal" / "corpus" / "ajryan_B1Budget_M.rpt").exists():
            pytest.skip("corpus .rpt not present")
        found = rpt_viewer.find_original("ajryan_B1Budget_M.xml")
        assert found is not None and found.suffix == ".rpt"

    def test_authored_dump_has_no_binary(self):
        """cr_demo dumps are authored by build_ladder.py — there is no
        Crystal original, and the UI must not offer to open one."""
        assert rpt_viewer.find_original("09_branch_activity_matrix.xml") is None

    def test_unknown_dump_is_none(self):
        assert rpt_viewer.find_original("no_such_report_at_all.xml") is None

    def test_path_traversal_in_the_name_finds_nothing(self):
        assert rpt_viewer.find_original("../../../../etc/passwd") is None
        assert rpt_viewer.find_original("..") is None


class TestDemoScenario:
    """The 'Try Crystal Reports' button has to survive a live demo: a real
    report, its binary beside it, and saved data so the viewer shows rows
    without a database."""

    def test_the_try_sample_is_a_real_report_with_its_binary(self):
        from pentaho_migration.reports.api import SAMPLE_FILE
        assert SAMPLE_FILE.is_file()
        assert SAMPLE_FILE.with_suffix(".rpt").is_file(), (
            "the Try scenario must ship its .rpt - an authored dump cannot be "
            "opened in the viewer, which is the first step of the demo")

    def test_the_try_sample_renders_without_a_database(self):
        from pentaho_migration.reports.api import SAMPLE_FILE
        from pentaho_migration.reports.classify import has_saved_data
        assert has_saved_data(SAMPLE_FILE), (
            "the Try scenario must carry saved data, or the viewer shows an "
            "empty layout until someone supplies --server/--db credentials")

    def test_the_launcher_finds_the_try_sample_original(self):
        from pentaho_migration.reports.api import SAMPLE_NAME
        found = rpt_viewer.find_original(SAMPLE_NAME)
        assert found is not None and found.suffix == ".rpt"


class TestBounds:
    def test_refuses_a_path_outside_the_allowed_roots(self, tmp_path):
        outside = tmp_path / "elsewhere.rpt"
        outside.write_bytes(b"not really a report")
        with pytest.raises((ValueError, RuntimeError)) as excinfo:
            rpt_viewer.open_original(outside)
        # either "viewer not built" or the refusal — never a launch
        assert "refusing" in str(excinfo.value) or "not built" in str(excinfo.value)

    def test_refuses_a_non_rpt_inside_an_allowed_root(self):
        dump = REPO / "samples" / "cr_demo" / "09_branch_activity_matrix.xml"
        if not dump.exists():
            pytest.skip("demo dump not present")
        with pytest.raises((ValueError, RuntimeError)):
            rpt_viewer.open_original(dump)

    def test_launches_only_the_bundled_viewer(self):
        """The executable is fixed in code — never taken from the request."""
        source = Path(rpt_viewer.__file__).read_text(encoding="utf-8")
        assert "VIEWER = REPO_ROOT" in source
        assert "shell=False" in source


class TestApi:
    def test_status_reports_availability_and_a_reason(self):
        body = client.get("/reports/original?dump=09_branch_activity_matrix.xml").json()
        assert body["available"] is False
        assert body["original"] is None
        assert body["reason"]          # always explains why not

    def test_status_for_an_extracted_report(self):
        if not (REPO / "samples" / "crystal" / "corpus" / "ajryan_B1Budget_M.rpt").exists():
            pytest.skip("corpus .rpt not present")
        body = client.get("/reports/original?dump=ajryan_B1Budget_M.xml").json()
        if rpt_viewer.viewer_available():
            assert body["available"] is True
            assert body["original"].endswith(".rpt")
        else:
            assert body["available"] is False
            assert "not built" in body["reason"]

    def test_open_without_a_binary_is_404(self):
        res = client.post("/reports/original/open",
                          json={"dump": "09_branch_activity_matrix.xml"})
        assert res.status_code == 404
        assert "authored dumps" in res.json()["detail"]

    def test_remote_caller_is_refused(self, monkeypatch):
        """Only the machine running the app may launch a desktop process."""
        called = []
        monkeypatch.setattr(rpt_viewer, "open_original",
                            lambda p: called.append(p))
        res = remote_client.post("/reports/original/open",
                                 json={"dump": "ajryan_B1Budget_M.xml"})
        assert res.status_code == 403
        assert called == []

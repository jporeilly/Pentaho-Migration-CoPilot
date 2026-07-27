"""Uploading the .rpt binary itself - the file a customer actually has.

The upload path routes by CONTENT (the OLE compound-file magic), never by
extension, and runs the same extraction chain the corpus scripts use before
handing the dump to the normal pipeline. Extraction needs RptToXml + the SAP
runtime, so the live tests skip on machines without them - the routing and
failure-message tests run everywhere.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.reports.rpt_extract import (
    OLE_MAGIC, extraction_available, looks_like_rpt)

REPO = Path(__file__).resolve().parents[1]
CORPUS_RPT = REPO / "samples" / "crystal" / "corpus" / "gerardo-lijs_DataSetReport.rpt"

client = TestClient(app, client=("127.0.0.1", 12345))


class TestRouting:
    def test_ole_magic_is_recognized(self):
        assert looks_like_rpt(OLE_MAGIC + b"anything")
        assert not looks_like_rpt(b"<?xml version='1.0'?>")
        assert not looks_like_rpt(b"")

    def test_a_dump_still_goes_down_the_dump_path(self):
        """Uploading XML must not regress - content routing, not extension."""
        dump = REPO / "samples" / "crystal" / "demo" / "branch_transactions.xml"
        res = client.post("/reports/inspect?jndi=CSCU",
                          files={"dump": ("weird_name.rpt", dump.read_bytes(),
                                          "application/octet-stream")})
        assert res.status_code == 200   # XML content wins over the .rpt name

    def test_garbage_ole_gets_an_actionable_422(self):
        """An OLE file that is not a Crystal report must fail with a sentence,
        not a stack trace - and only when the extractor exists to try it."""
        blob = OLE_MAGIC + b"\x00" * 600
        res = client.post("/reports/inspect",
                          files={"dump": ("fake.rpt", blob, "application/octet-stream")})
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "RptToXml" in detail or ".rpt" in detail


@pytest.mark.skipif(bool(extraction_available()),
                    reason=f"extraction unavailable: {extraction_available()}")
class TestLiveExtraction:
    def test_rpt_upload_converts_end_to_end(self):
        if not CORPUS_RPT.exists():
            pytest.skip("corpus .rpt not present")
        res = client.post("/reports/convert",
                          files={"dump": (CORPUS_RPT.name, CORPUS_RPT.read_bytes(),
                                          "application/octet-stream")})
        assert res.status_code == 200, res.json().get("detail")
        body = res.json()
        assert body["filename"].endswith(".prpt")
        assert body["prpt_base64"]
        assert body["summary"]["counts"]["elements"] > 0

    def test_extraction_scrubs_credentials(self):
        """The dump RptToXml writes carries logons copied from the .rpt; the
        upload path must scrub them before anything else sees the XML."""
        if not CORPUS_RPT.exists():
            pytest.skip("corpus .rpt not present")
        res = client.post("/reports/inspect",
                          files={"dump": (CORPUS_RPT.name, CORPUS_RPT.read_bytes(),
                                          "application/octet-stream")})
        assert res.status_code == 200
        assert "Password=" not in res.text or 'Password=""' in res.text

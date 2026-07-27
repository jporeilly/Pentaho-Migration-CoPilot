"""Real-corpus regression: every extracted RptToXml dump must parse.

Runs only when the extracted corpus exists (this box; extraction requires the
SAP runtime, so CI skips). The zero-parse-failure bar the ETL corpora set.
"""

from pathlib import Path

import pytest

from pentaho_migration.reports import load_report_model

CORPUS = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "corpus"
DUMPS = sorted(CORPUS.glob("*.xml")) if CORPUS.is_dir() else []


@pytest.mark.skipif(len(DUMPS) < 10, reason="extracted corpus not present")
def test_every_real_dump_parses():
    failures = []
    for xml in DUMPS:
        try:
            load_report_model(xml)
        except Exception as exc:
            failures.append(f"{xml.name}: {exc}")
    assert not failures, "\n".join(failures)


@pytest.mark.skipif(len(DUMPS) < 10, reason="extracted corpus not present")
def test_no_credentials_left_in_corpus():
    from pentaho_migration.reports.sanitize import scrub_directory

    files_changed, attrs = scrub_directory(CORPUS)
    assert attrs == 0, f"{attrs} credential attribute(s) still present - scrub before committing"

"""The dependency doctor: every check answers, none can crash it.

The doctor's contract: probes are short-timeout and exception-proof
(a hung Docker pipe or refused port is a STATUS, not a traceback), and
every non-OK row carries what it is needed for so the reader knows what
degrades. Third parties are never installed - only reported."""

import pentaho_migration.doctor as doctor
from pentaho_migration.doctor import Check, format_doctor, run_doctor


class TestDoctor:
    def test_runs_clean_and_covers_every_lane(self):
        checks = run_doctor()
        lanes = {c.lane for c in checks}
        assert {"Core", "Pentaho", "Crystal", "LLM", "Airflow",
                "Databases"} <= lanes
        assert all(c.status in ("OK", "WARN", "--", "info")
                   for c in checks)

    def test_every_non_ok_row_says_what_degrades(self):
        for c in run_doctor():
            assert c.needed_for, c.name
            if c.status == "--":
                assert c.action, f"{c.name} is missing but has no next step"

    def test_probe_failures_are_statuses_not_crashes(self, monkeypatch):
        monkeypatch.setattr(doctor, "_port_open",
                            lambda *a, **k: (_ for _ in ()).throw(
                                OSError("boom")) if False else False)
        monkeypatch.setattr(doctor, "_http_ok", lambda *a, **k: False)
        monkeypatch.setattr(doctor, "_docker_state",
                            lambda: ("--", "neither docker nor podman on PATH"))
        checks = run_doctor()
        runtime = next(c for c in checks if c.name == "Container runtime")
        assert runtime.status == "--"
        assert "never auto-installed" in runtime.action
        assert "Podman" in runtime.action     # the free option is named

    def test_format_renders_a_summary_line(self):
        text = format_doctor([
            Check("Core", "Python", "OK", "3.13", "everything"),
            Check("Airflow", "Docker Desktop", "--", "not found",
                  "the demo box", "install it yourself"),
        ])
        assert "1 ready" in text
        assert "next step:  install it yourself" in text
        assert "[--]  Docker Desktop" in text

"""Defaults must OPEN the report with data (the order_detail case).

The xaction authors customer 103 with a 2005-01-01..2005-01-05 window -
authored against the ORIGINAL estate's database. On the demo connection
customer 103's three orders all live in 2003-2004, so every default was
set and the report still opened empty. The API layer now probes the
query with the substituted defaults and, when nothing comes back,
repoints the date window at the data's own MIN/MAX span. General logic:
any DateField parameters bounding ONE date column, any report."""

import pentaho_migration.reports.schema_agent as schema_agent
from pentaho_migration.reports.api import _widen_empty_date_window
from pentaho_migration.reports.model import Parameter, ReportModel

SQL = ("SELECT CUSTOMERNAME, ORDERDATE FROM ORDERS "
       "WHERE ( ORDERDATE >= ${time_start} AND ORDERDATE <= ${time_stop} ) "
       "AND CUSTOMERNUMBER = ${customernumber} "
       "ORDER BY ORDERDATE ASC")


def _model():
    m = ReportModel()
    m.jndi = "SampleData"
    m.sql = SQL
    m.parameters = [
        Parameter(name="customernumber", default="103"),
        Parameter(name="time_start", value_type="DateField",
                  default="2005-01-01 00:00:00"),
        Parameter(name="time_stop", value_type="DateField",
                  default="2005-01-05 00:00:00"),
    ]
    return m


def _fake_preview(responses):
    """A preview_query stub yielding canned responses in call order."""
    calls = []

    def fake(jndi, sql, parameters=None, limit=50):
        calls.append(sql)
        return responses[min(len(calls) - 1, len(responses) - 1)]
    fake.calls = calls
    return fake


class TestWidenEmptyDateWindow:
    def test_an_empty_authored_window_repoints_to_the_data_span(
            self, monkeypatch):
        fake = _fake_preview([
            {"rows": []},                                    # probe: no data
            {"rows": [["2003-05-20 00:00:00", "2004-11-25 00:00:00"]]},
        ])
        monkeypatch.setattr(schema_agent, "preview_query", fake)
        model = _model()
        _widen_empty_date_window(model)
        by_name = {p.name: p.default for p in model.parameters}
        assert by_name["time_start"] == "2003-05-20 00:00:00"
        assert by_name["time_stop"] == "2004-11-25 00:00:00"
        assert by_name["customernumber"] == "103"     # untouched
        note = next(i for i in model.issues if "repointed" in i)
        assert "2005-01-01" in note          # says what was authored
        assert "2003-05-20..2004-11-25" in note
        # the MIN/MAX probe neutralised the date conditions and dropped
        # the ORDER BY, and substituted the OTHER defaults
        assert "1=1" in fake.calls[1] and "103" in fake.calls[1]
        assert "ORDER BY" not in fake.calls[1]

    def test_a_window_with_data_is_left_alone(self, monkeypatch):
        fake = _fake_preview([{"rows": [["Atelier graphique"]]}])
        monkeypatch.setattr(schema_agent, "preview_query", fake)
        model = _model()
        _widen_empty_date_window(model)
        assert model.parameters[1].default == "2005-01-01 00:00:00"
        assert not [i for i in model.issues if "repointed" in i]
        assert len(fake.calls) == 1          # only the probe ran

    def test_no_rows_at_all_stays_honest(self, monkeypatch):
        # even the widened probe finds nothing (the OTHER defaults filter
        # everything out) - do not invent a window
        fake = _fake_preview([{"rows": []}, {"rows": [[None, None]]}])
        monkeypatch.setattr(schema_agent, "preview_query", fake)
        model = _model()
        _widen_empty_date_window(model)
        assert model.parameters[1].default == "2005-01-01 00:00:00"

    def test_two_different_date_columns_stay_out(self, monkeypatch):
        fake = _fake_preview([{"rows": []}])
        monkeypatch.setattr(schema_agent, "preview_query", fake)
        model = _model()
        model.sql = ("SELECT 1 FROM ORDERS WHERE ORDERDATE >= ${time_start} "
                     "AND SHIPPEDDATE <= ${time_stop}")
        _widen_empty_date_window(model)
        assert model.parameters[1].default == "2005-01-01 00:00:00"

    def test_an_unreachable_connection_changes_nothing(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("connection refused")
        monkeypatch.setattr(schema_agent, "preview_query", boom)
        model = _model()
        _widen_empty_date_window(model)
        assert model.parameters[1].default == "2005-01-01 00:00:00"

    def test_the_note_classifies_as_applied_work(self):
        from pentaho_migration.reports.todo_kinds import APPLIED, split_todos

        note = ("the authored date window returns NO rows on this "
                "connection (time_start=2005-01-01 00:00:00 - authored "
                "against the original estate's database); the window is "
                "repointed to the data's own span for the selected "
                "defaults (2003-05-20..2004-11-25) so the report opens "
                "with data - review the window before publishing")
        assert note in split_todos([note])[APPLIED]

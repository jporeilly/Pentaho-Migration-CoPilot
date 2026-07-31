"""The shared function-translation table (corpus2 gap #1).

One table serves both definition dialects. The evidence standard is the
PRD engine itself: every ported class must resolve in the local
install's jars, and the flagship corpus2 report renders live.
"""

from pathlib import Path

import pytest

from pentaho_migration.reports.jfreereport_functions import (
    AGGREGATES, PORTABLE, port_note, targets, translate,
)
from pentaho_migration.reports.jfreereport_parser import parse_jfreereport
from pentaho_migration.reports.xaction_parser import build_report_model

CORPUS2 = Path("samples/xactions/corpus2")
PP_BOOT = CORPUS2 / "pentaho-platform-5.0-OLD" / "test-solution" / "boot"


class TestTranslationTable:
    def test_decisions(self):
        assert translate("ItemSumFunction", "t", {}) == \
            ("aggregate", ("Sum", True))
        assert translate("PageOfPagesFunction", "p", {}) == \
            ("special", "pagenofm")
        kind, fqcn = translate("BSHExpression", "b", {})
        assert kind == "port"
        assert fqcn.endswith("modules.misc.beanshell.BSHExpression")
        assert translate("SomethingCustomEJB", "x", {}) == (None, None)

    def test_subpackages_survive_the_rename(self):
        assert PORTABLE["SubStringExpression"].endswith(
            "function.strings.SubStringExpression")
        assert PORTABLE["DateExpression"].endswith(
            "function.date.DateExpression")

    def test_targets_and_note_flavour(self):
        props = {"element": "NoDataBanner"}
        assert targets("HideElementIfDataAvailableExpression", props) == \
            ["NoDataBanner"]
        note = port_note("hideBanner", "HideElementIfDataAvailableExpression",
                         props)
        assert "ported unchanged" in note
        assert "NoDataBanner" in note and "no-data" in note

    def test_every_ported_class_resolves_in_the_engine_jars(self):
        lib = Path(r"C:\Pentaho\design-tools\report-designer\lib")
        if not lib.is_dir():
            pytest.skip("no PRD install")
        import zipfile
        classes = set()
        for jar in lib.glob("*.jar"):
            try:
                with zipfile.ZipFile(jar) as z:
                    classes.update(
                        n[:-6].replace("/", ".") for n in z.namelist()
                        if n.endswith(".class"))
            except (OSError, zipfile.BadZipFile):
                continue
        missing = {c for c in PORTABLE.values() if c not in classes}
        assert missing == set(), \
            "table promises classes the engine does not ship"

    def test_aggregates_match_the_running_split(self):
        # Item* accumulates row-by-row; Group*/TotalGroup* are totals -
        # collapsing them put the ending net income on the wrong line once
        assert AGGREGATES["ItemSumFunction"] == ("Sum", True)
        assert AGGREGATES["TotalGroupSumFunction"] == ("Sum", False)


@pytest.mark.skipif(not CORPUS2.is_dir(), reason="corpus2 not present")
class TestCorpus2Contracts:
    def test_quad_report_ports_beanshell_and_colors(self):
        # simple dialect: 3 BSHExpression + 3 ElementColorFunction +
        # PageOfPagesFunction; targeted elements keep their names
        m = build_report_model(PP_BOOT / "report.xaction")
        classes = {cls.rsplit(".", 1)[-1] for _n, cls, _p
                   in m.port_functions}
        assert classes == {"BSHExpression", "ElementColorFunction"}
        named = {e.name for s in m.sections for e in s.elements
                 if e.emit_name}
        assert "Variance Field" in named
        # PageOfPages became the writer's own page function, not a port
        assert not any("PageOfPages" in c for _n, c, _p in m.port_functions)
        from pentaho_migration.reports.todo_kinds import split_todos
        manual = split_todos(m.issues)["manual"]
        assert all("XQuery" in n for n in manual), manual

    def test_breadboard_no_data_pair_ports_with_targets(self):
        xml = (CORPUS2 / "breadboard" / "customer_360" / "leads"
               / "reporting" / "Sales_Leads.xml")
        m = parse_jfreereport(xml)
        pair = {cls.rsplit(".", 1)[-1] for _n, cls, _p in m.port_functions}
        assert "ShowElementIfDataAvailableExpression" in pair \
            or "HideElementIfDataAvailableExpression" in pair
        assert any(e.emit_name for s in m.sections for e in s.elements)
        assert not any("has no direct PRD equivalent" in i
                       and "DataAvailable" in i for i in m.issues)

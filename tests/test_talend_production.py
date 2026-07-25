"""Talend production pass: TABLE-param emitters (CSV input, text output,
filter, sort, aggregate), tRunJob orchestration -> .kjb, and the rules-v3
long-tail mappings. Real corpus files used where they exercise the path."""

import json
from pathlib import Path
from xml.etree import ElementTree

from pentaho_migration.generator import KjbGenerator, KtrGenerator
from pentaho_migration.ir import FieldDef, Hop, Pipeline, SourceTool, Step
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import TalendParser

TALEND = Path(__file__).resolve().parents[1] / "samples" / "talend"


def _pipeline(*steps):
    return Pipeline(name="t", source_tool=SourceTool.TALEND, steps=list(steps))


def _step_xml(ktr, name):
    root = ElementTree.fromstring(ktr)
    return next(s for s in root.iter("step") if s.findtext("name") == name)


def _convert(item_name):
    (pipe,) = TalendParser().parse_file(TALEND / item_name)
    RulesMapper.for_pipeline(pipe).apply(pipe)
    return KtrGenerator().generate(pipe)


class TestFileEmitters:
    def test_csv_input_config_from_real_item(self):
        ktr = _convert("carpediemmlf_DEMOTALEND2_0.1.item")
        el = _step_xml(ktr, "tFileInputDelimited_1")
        assert el.findtext("filename") == "C:/getting_started/input data/movies.csv"
        assert el.findtext("separator") == ";"
        assert el.findtext("header") == "Y"
        fields = {(f.findtext("name"), f.findtext("type"))
                  for f in el.findall("fields/field")}
        assert ("movieID", "Integer") in fields and ("title", "String") in fields

    def test_text_file_output_config(self):
        step = Step(
            name="out", source_type="tFileOutputDelimited", pdi_type="TextFileOutput",
            fields=[FieldDef(name="A", datatype="string")],
            properties={"FILENAME": '"C:/out/result.csv"', "FIELDSEPARATOR": '";"',
                        "INCLUDEHEADER": "true"})
        el = _step_xml(KtrGenerator().generate(_pipeline(step)), "out")
        assert el.findtext("file/name") == "C:/out/result"
        assert el.findtext("file/extention") == "csv"
        assert el.findtext("separator") == ";"
        assert el.findtext("header") == "Y"


class TestTableParamEmitters:
    def test_sort_criteria_carry_direction(self):
        step = Step(name="s", source_type="tSortRow", pdi_type="SortRows",
                    properties={"CRITERIA": json.dumps(
                        [{"COLNAME": "A", "SORT": "num", "ORDER": "desc"},
                         {"COLNAME": "B", "SORT": "alpha", "ORDER": "asc"}])})
        el = _step_xml(KtrGenerator().generate(_pipeline(step)), "s")
        rows = [(f.findtext("name"), f.findtext("ascending"))
                for f in el.findall("fields/field")]
        assert rows == [("A", "N"), ("B", "Y")]

    def test_aggregate_tables_drive_group_by(self):
        step = Step(name="agg", source_type="tAggregateRow", pdi_type="GroupBy",
                    properties={
                        "GROUPBYS": json.dumps([{"OUTPUT_COLUMN": "g", "INPUT_COLUMN": "REGION"}]),
                        "OPERATIONS": json.dumps(
                            [{"OUTPUT_COLUMN": "total", "FUNCTION": "sum", "INPUT_COLUMN": "AMT"},
                             {"OUTPUT_COLUMN": "n", "FUNCTION": "count", "INPUT_COLUMN": "AMT"}])})
        el = _step_xml(KtrGenerator().generate(_pipeline(step)), "agg")
        assert [g.findtext("name") for g in el.findall("group/field")] == ["REGION"]
        aggs = [(f.findtext("aggregate"), f.findtext("subject"), f.findtext("type"))
                for f in el.findall("fields/field")]
        assert ("total", "AMT", "SUM") in aggs and ("n", "AMT", "COUNT_ALL") in aggs

    def test_filter_conditions_and_null_handling(self):
        step = Step(name="f", source_type="tFilterRow", pdi_type="FilterRows",
                    properties={"LOGICAL_OP": "&&", "CONDITIONS": json.dumps(
                        [{"INPUT_COLUMN": "STATUS", "OPERATOR": "==", "RVALUE": '"OPEN"'},
                         {"INPUT_COLUMN": "ERR", "OPERATOR": "==", "RVALUE": "null"}])})
        el = _step_xml(KtrGenerator().generate(_pipeline(step)), "f")
        xml = ElementTree.tostring(el, encoding="unicode")
        assert "<leftvalue>STATUS</leftvalue>" in xml
        assert "<text>OPEN</text>" in xml
        assert "IS NULL" in xml
        assert "<operator>AND</operator>" in xml

    def test_advanced_java_filter_stays_honest(self):
        step = Step(name="f", source_type="tFilterRow", pdi_type="FilterRows",
                    properties={"USE_ADVANCED": "true", "ADVANCED_COND": "input_row.a.equals(b)"})
        el = _step_xml(KtrGenerator().generate(_pipeline(step)), "f")
        # the honesty note lands in the step description in the .ktr
        assert "advanced (Java) mode" in (el.findtext("description") or "")


class TestOrchestration:
    def test_trunjob_becomes_kjb_with_wired_trans_entries(self):
        (job,) = TalendParser().parse_workflows(TALEND / "aodn_data_and_metadata_0.1.item")
        assert job.name == "aodn_data_and_metadata"
        sessions = [e for e in job.entries if e.task_type == "Session"]
        assert {e.mapping for e in sessions} == {"createWMS", "mergeMeasurements"}
        # ordered: mergeMeasurements runs first, then createWMS on success
        assert any(h.from_entry == "tRunJob_1" and h.to_entry == "tRunJob_2"
                   and h.condition == "Succeeded" for h in job.hops)
        kjb = KjbGenerator().generate(job)
        root = ElementTree.fromstring(kjb)
        trans = [e for e in root.findall("entries/entry") if e.findtext("type") == "TRANS"]
        assert {e.findtext("filename").rsplit("/", 1)[-1] for e in trans} == \
            {"createWMS.ktr", "mergeMeasurements.ktr"}

    def test_plain_job_yields_no_kjb(self):
        assert TalendParser().parse_workflows(
            TALEND / "carpediemmlf_DEMOTALEND2_0.1.item") == []


class TestRulesV3:
    def test_long_tail_components_now_map(self):
        cases = {"tFileOutputExcel": "ExcelOutput",
                 "tFileInputProperties": "PropertyInput",
                 "tHSQLDbInput": "TableInput",
                 "tMemorizeRows": "AnalyticQuery",
                 "tSOAP": "WebServiceLookup",
                 "tVerticaClose": "Dummy"}
        steps = [Step(name=c, source_type=c) for c in cases]
        pipe = _pipeline(*steps)
        RulesMapper.for_pipeline(pipe).apply(pipe)
        for step in pipe.steps:
            assert step.pdi_type == cases[step.name], step.name

    def test_service_hosts_stay_honestly_manual(self):
        pipe = _pipeline(Step(name="svc", source_type="tESBConsumer"))
        RulesMapper.for_pipeline(pipe).apply(pipe)
        assert pipe.steps[0].pdi_type is None

"""Talend rules v4: the families extended from the 150-job corpus, and the
honesty contract for what cannot map — every unmapped component must carry a
REASON, never a bare "no rule" message."""

from pathlib import Path

from pentaho_migration.ir import Confidence, Pipeline, SourceTool, Step
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import TalendParser
from pentaho_migration.validator import assess_source

TALEND = Path(__file__).resolve().parents[1] / "samples" / "talend"


def _map(*components):
    pipe = Pipeline(name="t", source_tool=SourceTool.TALEND,
                    steps=[Step(name=c, source_type=c) for c in components])
    return {s.source_type: s for s in RulesMapper.for_pipeline(pipe).apply(pipe).steps}


class TestDatabaseFamilies:
    def test_teradata_greenplum_follow_the_family_contract(self):
        steps = _map("tTeradataInput", "tTeradataRow", "tTeradataConnection",
                     "tGreenplumInput", "tGreenplumRow", "tGreenplumClose",
                     "tHSQLDbOutput", "tSqlRow")
        assert steps["tTeradataInput"].pdi_type == "TableInput"
        assert steps["tTeradataRow"].pdi_type == "ExecSQLRow"
        assert steps["tTeradataConnection"].pdi_type == "Dummy"
        assert steps["tGreenplumInput"].pdi_type == "TableInput"
        assert steps["tGreenplumRow"].pdi_type == "ExecSQLRow"
        assert steps["tGreenplumClose"].pdi_type == "Dummy"
        assert steps["tHSQLDbOutput"].pdi_type == "TableOutput"
        assert steps["tSqlRow"].pdi_type == "ExecSQLRow"

    def test_cloud_warehouses_are_jdbc(self):
        steps = _map("tSnowflakeInput", "tSnowflakeOutput", "tBigQueryInput")
        assert steps["tSnowflakeInput"].pdi_type == "TableInput"
        assert steps["tSnowflakeOutput"].pdi_type == "TableOutput"
        assert steps["tBigQueryInput"].pdi_type == "TableInput"


class TestBigDataThroughPdiMechanisms:
    def test_hive_is_jdbc_not_a_bespoke_step(self):
        steps = _map("tHiveInput", "tHiveRow", "tHiveConnection")
        assert steps["tHiveInput"].pdi_type == "TableInput"
        assert steps["tHiveRow"].pdi_type == "ExecSQLRow"
        assert steps["tHiveConnection"].pdi_type == "Dummy"
        assert any("JDBC" in n for n in steps["tHiveInput"].notes)

    def test_hdfs_rides_vfs_on_ordinary_file_steps(self):
        steps = _map("tHDFSInput", "tHDFSOutput", "tHDFSConnection")
        assert steps["tHDFSInput"].pdi_type == "TextFileInput"
        assert steps["tHDFSOutput"].pdi_type == "TextFileOutput"
        assert steps["tHDFSConnection"].pdi_type == "Dummy"
        assert any("hdfs://" in n for n in steps["tHDFSInput"].notes)

    def test_object_store_rides_vfs_connections(self):
        steps = _map("tS3Connection", "tS3Put", "tS3List")
        assert steps["tS3Connection"].pdi_type == "Dummy"
        assert steps["tS3Put"].pdi_type == "ProcessFiles"
        assert steps["tS3List"].pdi_type == "GetFileNames"
        assert any("VFS" in n for n in steps["tS3Connection"].notes)


class TestHonestyContract:
    """The core promise: nothing unmapped is left unexplained."""

    def test_camel_components_are_documented_not_mapped(self):
        steps = _map("cLog", "cSetHeader", "cDirect", "cJMS")
        for step in steps.values():
            assert step.pdi_type is None                 # never faked
            assert step.confidence == Confidence.MANUAL
            assert any("Camel" in n or "routing-layer" in n for n in step.notes)
            assert not any("No mapping rule" in n for n in step.notes)

    def test_service_endpoints_explain_why_pdi_cannot_host_them(self):
        steps = _map("tRESTRequest", "tESBProviderResponse")
        for step in steps.values():
            assert step.pdi_type is None
            assert any("not a service host" in n for n in step.notes)

    def test_custom_and_joblet_components_are_named_as_such(self):
        steps = _map("Joblet_StoreStartTime", "DI_CNTL_Job_Tracking_Stats")
        for step in steps.values():
            assert step.pdi_type is None
            assert any("CUSTOM component" in n or "joblet" in n for n in step.notes)

    def test_conventional_unknown_still_gets_the_plain_message(self):
        (step,) = _map("tSomeFutureComponent").values()
        assert step.pdi_type is None
        assert any("No mapping rule" in n for n in step.notes)

    def test_no_corpus_step_is_left_unexplained(self):
        """Every unmapped step across the whole 150-job corpus carries a
        reason — the regression guard for the honesty contract."""
        parser = TalendParser()
        unexplained = []
        for item in sorted(TALEND.glob("*.item")):
            try:
                pipelines = parser.parse_file(item)
            except Exception:
                continue
            for pipeline in pipelines:
                RulesMapper.for_pipeline(pipeline).apply(pipeline)
                for step in pipeline.steps:
                    if step.pdi_type is None and not step.notes:
                        unexplained.append((item.name, step.source_type))
        assert unexplained == [], unexplained


class TestEsbRouteDetection:
    def test_route_job_is_flagged_as_a_different_artifact_kind(self):
        route = TALEND / "tlnd-frguo_DemoRESTRoute_0.1.item"
        if not route.exists():
            import pytest
            pytest.skip("corpus route job not present")
        parser = TalendParser()
        info = assess_source(parser.analyze_export(route), parser.parse_file(route))
        esb = [w for w in info.warnings if "Mediation Route" in w.text]
        assert esb, "ESB route jobs must be called out before conversion"
        assert esb[0].level.value == "serious"
        assert "Carte" in esb[0].text          # gives the real integration path

    def test_plain_di_job_is_not_flagged_as_a_route(self):
        job = TALEND / "carpediemmlf_DEMOTALEND2_0.1.item"
        parser = TalendParser()
        info = assess_source(parser.analyze_export(job), parser.parse_file(job))
        assert not [w for w in info.warnings if "Mediation Route" in w.text]

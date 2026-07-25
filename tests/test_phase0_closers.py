"""Phase 0 closers: remaining step configs, Workflow->Job conversion, PDI runner."""

from pathlib import Path
from xml.etree import ElementTree

from pentaho_migration.generator import KjbGenerator, KtrGenerator
from pentaho_migration.ir import Confidence, FieldDef, Hop, Pipeline, SourceTool, Step
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import PowerCenterParser
from pentaho_migration.pdi_runner import EXIT_CODES, RunResult, find_pdi_home, run_artifact

HHS = Path(__file__).resolve().parents[1] / "samples" / "informatica" / "hhs_comptime.xml"


def _pipeline(*steps, hops=()):
    return Pipeline(
        name="t", source_tool=SourceTool.POWERCENTER,
        steps=list(steps), hops=[Hop(from_step=a, to_step=b) for a, b in hops],
    )


def _step_xml(ktr: str, name: str):
    root = ElementTree.fromstring(ktr)
    return next(s for s in root.iter("step") if s.findtext("name") == name)


class TestMergeJoin:
    def test_keys_type_and_inputs(self):
        join = Step(
            name="JNR", source_type="Joiner", pdi_type="MergeJoin",
            confidence=Confidence.AUTO,
            properties={"Join Condition": "ID = MEMBER_ID AND YEAR = YR",
                        "Join Type": "Detail Outer Join"},
        )
        pipeline = _pipeline(
            Step(name="A", source_type="Source Qualifier", pdi_type="TableInput"),
            Step(name="B", source_type="Source Qualifier", pdi_type="TableInput"),
            join,
            hops=[("A", "JNR"), ("B", "JNR")],
        )
        el = _step_xml(KtrGenerator().generate(pipeline), "JNR")
        assert el.findtext("join_type") == "LEFT OUTER"
        assert el.findtext("step1") == "A"
        assert el.findtext("step2") == "B"
        assert [k.text for k in el.findall("keys_1/key")] == ["ID", "YEAR"]
        assert [k.text for k in el.findall("keys_2/key")] == ["MEMBER_ID", "YR"]


class TestStreamLookup:
    def _lookup_pipeline(self):
        lookup = Step(
            name="LKP", source_type="Lookup Procedure", pdi_type="StreamLookup",
            fields=[FieldDef(name="MEMBER_ID"), FieldDef(name="MEMBER_NAME")],
            properties={"Lookup condition": "MEMBER_ID = IN_ID",
                        "Lookup table name": "MEMBERS"},
        )
        return _pipeline(
            Step(name="SRC", source_type="Source Qualifier", pdi_type="TableInput"),
            lookup,
            hops=[("SRC", "LKP")],
        )

    def test_lookup_source_injected(self):
        ktr = KtrGenerator().generate(self._lookup_pipeline())
        src = _step_xml(ktr, "LKP_lookup_src")
        assert src.findtext("type") == "TableInput"
        assert "SELECT * FROM MEMBERS" in src.findtext("sql")
        root = ElementTree.fromstring(ktr)
        hops = {(h.findtext("from"), h.findtext("to")) for h in root.findall("order/hop")}
        assert ("LKP_lookup_src", "LKP") in hops

    def test_keys_and_values(self):
        el = _step_xml(KtrGenerator().generate(self._lookup_pipeline()), "LKP")
        assert el.findtext("from") == "LKP_lookup_src"
        key = el.find("lookup/key")
        assert key.findtext("name") == "IN_ID"       # stream side
        assert key.findtext("field") == "MEMBER_ID"  # lookup side
        values = [v.findtext("name") for v in el.findall("lookup/value")]
        assert values == ["MEMBER_NAME"]

    def test_caller_pipeline_not_mutated(self):
        pipeline = self._lookup_pipeline()
        KtrGenerator().generate(pipeline)
        assert pipeline.step("LKP_lookup_src") is None


class TestInsertUpdateAndDbProc:
    def test_insert_update_targets_downstream(self):
        upd = Step(
            name="UPD", source_type="Update Strategy", pdi_type="InsertUpdate",
            fields=[FieldDef(name="ID"), FieldDef(name="STATUS")],
        )
        pipeline = _pipeline(
            upd, Step(name="T_MEMBERS", source_type="Target", pdi_type="TableOutput"),
            hops=[("UPD", "T_MEMBERS")],
        )
        el = _step_xml(KtrGenerator().generate(pipeline), "UPD")
        assert el.findtext("lookup/table") == "T_MEMBERS"
        # target has no key fields -> update values fall back to the step's own
        assert [v.findtext("name") for v in el.findall("lookup/value")] == ["ID", "STATUS"]

    def test_insert_update_infers_keys_from_target_primary_key(self):
        """The match keys come from the target's PRIMARY KEY fields, not from
        the update-strategy transform (which never names them)."""
        upd = Step(name="UPD", source_type="Update Strategy", pdi_type="InsertUpdate",
                   fields=[FieldDef(name="CUST_ID"), FieldDef(name="AMT")])
        target = Step(name="T_CUST", source_type="Target", fields=[
            FieldDef(name="CUST_ID", attrs={"KEYTYPE": "PRIMARY KEY"}),
            FieldDef(name="AMT"), FieldDef(name="NAME")])
        pipeline = _pipeline(upd, target, hops=[("UPD", "T_CUST")])
        el = _step_xml(KtrGenerator().generate(pipeline), "UPD")
        assert el.findtext("lookup/table") == "T_CUST"
        assert [k.findtext("name") for k in el.findall("lookup/key")] == ["CUST_ID"]
        assert el.find("lookup/key").findtext("condition") == "="
        # update columns are the target's NON-key fields
        assert [v.findtext("name") for v in el.findall("lookup/value")] == ["AMT", "NAME"]

    def test_target_primary_key_parsed_from_real_export(self):
        """A target INSTANCE carries its definition's PRIMARY KEY fields, so the
        generator can infer Insert/Update keys from the real corpus."""
        afps = HHS.parent / "hhs_cpm_afps.xml"
        pipelines = PowerCenterParser().parse_file(afps)
        keyed = [f.name for pipe in pipelines for s in pipe.steps
                 if s.source_type == "Target"
                 for f in s.fields if "PRIMARY" in f.attrs.get("KEYTYPE", "")]
        assert "PROCESS_NAME" in keyed

    def test_stored_procedure_now_maps(self):
        step = Step(
            name="SP_AUDIT", source_type="Stored Procedure",
            fields=[FieldDef(name="RUN_ID", datatype="integer")],
            properties={"Stored Procedure Name": "PKG_AUDIT.LOG_RUN"},
        )
        pipeline = _pipeline(step)
        RulesMapper().apply(pipeline)
        assert step.pdi_type == "DBProc"
        assert step.confidence == Confidence.REVIEW
        el = _step_xml(KtrGenerator().generate(pipeline), "SP_AUDIT")
        assert el.findtext("procedure") == "PKG_AUDIT.LOG_RUN"
        assert el.find("arguments/argument").findtext("name") == "RUN_ID"


class TestWorkflowToJob:
    def test_parse_workflows_from_real_export(self):
        (job,) = PowerCenterParser().parse_workflows(HHS)
        assert job.name == "wf_COMPTIME"
        sessions = [e for e in job.entries if e.task_type == "Session"]
        assert len(sessions) == 3
        assert all(s.mapping and s.mapping.startswith("m_COMPTIME") for s in sessions)
        assert len(job.hops) == 4
        conditional = [h for h in job.hops if h.condition]
        assert conditional and "Succeeded" in conditional[0].condition

    def test_kjb_generation(self):
        (job,) = PowerCenterParser().parse_workflows(HHS)
        kjb = KjbGenerator().generate(job)
        root = ElementTree.fromstring(kjb)
        assert root.findtext("name") == "wf_COMPTIME"
        entries = root.findall("entries/entry")
        types = [e.findtext("type") for e in entries]
        assert types.count("TRANS") == 3
        assert "SPECIAL" in types              # Start entry
        assert "MAIL" in types                 # Email task now converts
        trans = next(e for e in entries if e.findtext("type") == "TRANS")
        assert trans.findtext("filename").endswith(".ktr")
        assert len(root.findall("hops/hop")) == 4

    def test_email_task_converts_to_mail_entry(self):
        (job,) = PowerCenterParser().parse_workflows(HHS)
        kjb = KjbGenerator().generate(job)
        root = ElementTree.fromstring(kjb)
        mail = next(e for e in root.findall("entries/entry")
                    if e.findtext("type") == "MAIL")
        # recipient/subject/body carried from the Email task attributes
        assert mail.findtext("destination") == "$$WF_COMPTIME_EMAIL_LIST"
        assert mail.findtext("subject") == "$$WF_SUBJECT"
        assert mail.findtext("comment") == "$$WF_MESSAGE"

    def test_command_task_converts_to_shell_entry(self):
        from pentaho_migration.ir import Job, JobEntry
        job = Job(name="wf_x", entries=[
            JobEntry(name="Start", task_type="Start"),
            JobEntry(name="archive", task_type="Command",
                     commands=["mv a b", "rm c"])])
        root = ElementTree.fromstring(KjbGenerator().generate(job))
        shell = next(e for e in root.findall("entries/entry")
                     if e.findtext("type") == "SHELL")
        assert shell.findtext("insertScript") == "Y"
        assert shell.findtext("script") == "mv a b\nrm c"


class TestPdiRunner:
    def test_find_pdi_home_env(self, tmp_path, monkeypatch):
        (tmp_path / "Spoon.bat").write_text("rem fake")
        monkeypatch.setenv("PDI_HOME", str(tmp_path))
        assert find_pdi_home() == tmp_path

    def test_run_artifact_reports_exit_meaning(self, tmp_path, monkeypatch):
        (tmp_path / "Spoon.bat").write_text("rem fake")
        (tmp_path / "Pan.bat").write_text("rem fake")

        class Fake:
            returncode = 7
            stdout = "line1\nCould not load transformation\n"
            stderr = ""

        monkeypatch.setattr("subprocess.run", lambda *a, **k: Fake())
        result = run_artifact(tmp_path / "x.ktr", pdi_home=tmp_path)
        assert isinstance(result, RunResult)
        assert result.ok is False
        assert result.meaning == EXIT_CODES[7]
        assert "Could not load" in result.log_tail

class TestMappletExpansion:
    def test_mapplet_expanded_inline_from_real_export(self):
        """A mapplet instance's internal transformations are inlined into the
        parent pipeline (instead of vanishing), prefixed by the instance name,
        with the graph reconnected through the expansion."""
        cpm = HHS.parent / "hhs_cpm.xml"
        pipelines = PowerCenterParser().parse_file(cpm)
        expanded = [(p.name, s) for p in pipelines for s in p.steps
                    if any("expanded inline from mapplet" in n for n in s.notes)]
        assert expanded, "expected inlined mapplet steps"
        # the mapplet's Expression transforms survive expansion (their
        # expressions are then translatable)
        kinds = {s.source_type for _, s in expanded}
        assert "Expression" in kinds
        # no hop points at a step that doesn't exist (graph stays connected)
        for p in pipelines:
            names = {s.name for s in p.steps}
            for h in p.hops:
                assert h.from_step in names and h.to_step in names

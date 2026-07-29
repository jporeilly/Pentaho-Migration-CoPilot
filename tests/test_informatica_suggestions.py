"""Applying the Crystal principle to the Informatica workflow: a transformation
with no 1:1 PDI rule gets a SUGGESTED PDI approach (flagged for review), not a
bare "manual conversion required". Driven by the versioned _suggestions section
of the rules library - general and deterministic, not a per-pipeline hack.
"""

from pentaho_migration.ir import Confidence, Pipeline, SourceTool, Step
from pentaho_migration.mapper import RulesMapper


def _mapped(steps, tool=SourceTool.POWERCENTER):
    pipe = Pipeline(name="t", source_tool=tool, steps=steps)
    return {s.source_type: s for s in RulesMapper.for_pipeline(pipe).apply(pipe).steps}


class TestUnmappedGetsASuggestion:
    def test_a_known_category_gets_the_pdi_approach(self):
        s = _mapped([Step(name="ws", source_type="Web Services Consumer")])[
            "Web Services Consumer"]
        note = " ".join(s.notes)
        assert s.confidence == Confidence.MANUAL       # still needs a human
        assert "suggested approach" in note
        assert "Web services lookup" in note or "REST client" in note
        assert "manual conversion required" not in note   # the bare phrasing is gone

    def test_a_mapplet_is_pointed_at_a_pdi_mapping(self):
        note = " ".join(_mapped([Step(name="m", source_type="Mapplet")])["Mapplet"].notes)
        assert "sub-transformation" in note or "mapping" in note.lower()

    def test_an_unknown_powercenter_type_still_suggests_an_approach(self):
        note = " ".join(_mapped([Step(name="x", source_type="Frobnicator")])[
            "Frobnicator"].notes)
        # not the Talend message, and still names the general PDI approach
        assert "Talend" not in note
        assert "User Defined Java Class" in note


class TestMappedStepsAreUnaffected:
    def test_a_type_with_a_rule_still_maps_with_no_suggestion(self):
        s = _mapped([Step(name="a", source_type="Aggregator")])["Aggregator"]
        assert s.pdi_type == "GroupBy"
        assert not any("suggested approach" in n for n in s.notes)


class TestTalendStillGetsItsOwnHandoff:
    def test_a_custom_talend_component_keeps_the_studio_message(self):
        note = " ".join(_mapped([Step(name="c", source_type="myCustomThing")],
                                tool=SourceTool.TALEND)["myCustomThing"].notes)
        assert "CUSTOM component" in note or "joblet" in note

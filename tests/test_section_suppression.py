"""Conditional section suppression when several Crystal sections merge into
one PRD band — the single biggest fidelity gap in the corpus (52 of 93
EnableSuppress conditions used to be dropped with a note).

The condition cannot live on the merged band, so it moves to the section's own
elements: same condition, same rows, evaluated per element. The band keeps its
height where Crystal would have collapsed the section — that difference stays
called out in a note.
"""

import textwrap
from pathlib import Path

import pytest

from pentaho_migration.reports import load_report_model
from pentaho_migration.reports.formula_translator import translate_formula
from pentaho_migration.reports.todo_kinds import APPLIED, MANUAL, split_todos


def _dump(tmp_path, body):
    p = tmp_path / "r.xml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def _report(sections_xml):
    return f"""\
    <Report Name="S" FileName="s.rpt">
      <Database><Tables>
        <Table Name="O" Alias="O"><Fields>
          <Field Name="AMT" ValueType="NumberField"/>
          <Field Name="TYPE" ValueType="StringField"/>
        </Fields></Table>
      </Tables></Database>
      <DataDefinition><RecordSelectionFormula/></DataDefinition>
      <ReportDefinition><Areas>
        <Area Kind="Detail"><Sections>{sections_xml}</Sections></Area>
      </Areas></ReportDefinition>
    </Report>"""


SECTION_WITH_CONDITION = """\
    <Section Name="DetailSection1" Height="240">
      <SectionFormat EnableSuppress="False">
        <SectionAreaFormatConditionFormulas EnableSuppress="{O.AMT} &gt; 100"/>
      </SectionFormat>
      <ReportObjects>
        <TextObject Name="T1" Left="0" Top="0" Width="1440" Height="220"><Text>past due</Text></TextObject>
        <FieldObject Name="F1" Left="1500" Top="0" Width="1440" Height="220" DataSource="{O.AMT}"/>
      </ReportObjects>
    </Section>
    <Section Name="DetailSection2" Height="240">
      <ReportObjects>
        <FieldObject Name="F2" Left="0" Top="0" Width="1440" Height="220" DataSource="{O.TYPE}"/>
      </ReportObjects>
    </Section>"""


class TestPushDown:
    def test_condition_moves_to_the_sections_elements(self, tmp_path):
        model = load_report_model(_dump(tmp_path, _report(SECTION_WITH_CONDITION)))
        first = next(s for s in model.sections if s.name == "DetailSection1")
        for el in first.elements:
            keys = [k for k, _ in el.style_expressions]
            assert "visible" in keys, f"{el.name} lost the suppression condition"
        # Crystal suppresses when TRUE; PRD's visible shows when TRUE — inverted
        formula = dict(first.elements[0].style_expressions)["visible"]
        assert "NOT" in formula.upper() and "[AMT]" in formula

    def test_other_sections_elements_are_untouched(self, tmp_path):
        model = load_report_model(_dump(tmp_path, _report(SECTION_WITH_CONDITION)))
        second = next(s for s in model.sections if s.name == "DetailSection2")
        assert all("visible" not in dict(el.style_expressions)
                   for el in second.elements)

    def test_the_note_is_applied_not_manual(self, tmp_path):
        """The whole point: this is work the pipeline DID, and the height
        caveat is a verify — it must not land in the consultant's backlog."""
        model = load_report_model(_dump(tmp_path, _report(SECTION_WITH_CONDITION)))
        note = next(i for i in model.issues if "applied to the section's" in i)
        assert split_todos([note])[APPLIED] == [note]

    def test_untranslatable_condition_stays_manual(self, tmp_path):
        weird = SECTION_WITH_CONDITION.replace(
            "{O.AMT} &gt; 100", "drilldowngrouplevel &lt;&gt; 0")
        model = load_report_model(_dump(tmp_path, _report(weird)))
        first = next(s for s in model.sections if s.name == "DetailSection1")
        assert all("visible" not in dict(el.style_expressions)
                   for el in first.elements)
        manual = split_todos(model.issues)[MANUAL]
        assert any("not carried" in n for n in manual)

    def test_element_keeps_its_own_condition_too(self, tmp_path):
        both = SECTION_WITH_CONDITION.replace(
            '<TextObject Name="T1" Left="0" Top="0" Width="1440" Height="220">'
            "<Text>past due</Text></TextObject>",
            '<TextObject Name="T1" Left="0" Top="0" Width="1440" Height="220">'
            "<Text>past due</Text>"
            '<ObjectFormatConditionFormulas EnableSuppress="{O.TYPE} = &quot;X&quot;"/>'
            "</TextObject>")
        model = load_report_model(_dump(tmp_path, _report(both)))
        first = next(s for s in model.sections if s.name == "DetailSection1")
        formula = dict(first.elements[0].style_expressions)["visible"]
        assert formula.count("NOT") >= 2 and formula.startswith("=AND(")


AGG_CONDITION = SECTION_WITH_CONDITION.replace(
    "{O.AMT} &gt; 100", "Sum ({O.AMT}, {O.TYPE}) &gt; 100")


class TestAggregateSynthesis:
    """An aggregate inside a condition ("suppress unless Sum(...) > 0") cannot
    translate inline — OpenFormula has no windowed Sum. But the writer emits
    every model.summaries entry as a PRD report function, so the aggregate is
    synthesized as one and the condition references it by name."""

    def test_condition_aggregate_becomes_a_report_function(self, tmp_path):
        model = load_report_model(_dump(tmp_path, _report(AGG_CONDITION)))
        synth = next((s for s in model.summaries
                      if s.expression_name == "Sum_AMT_TYPE"), None)
        assert synth is not None
        assert synth.operation == "Sum" and synth.group_field == "TYPE"
        first = next(s for s in model.sections if s.name == "DetailSection1")
        formula = dict(first.elements[0].style_expressions)["visible"]
        assert "[Sum_AMT_TYPE]" in formula

    def test_equivalent_aggregates_share_one_function(self, tmp_path):
        twice = AGG_CONDITION + AGG_CONDITION.replace(
            "DetailSection1", "DetailSection3").replace(
            "DetailSection2", "DetailSection4")
        model = load_report_model(_dump(tmp_path, _report(twice)))
        assert sum(1 for s in model.summaries
                   if s.expression_name == "Sum_AMT_TYPE") == 1

    def test_unknown_aggregate_stays_manual(self, tmp_path):
        weird = SECTION_WITH_CONDITION.replace(
            "{O.AMT} &gt; 100", "Median ({O.AMT}, {O.TYPE}) &gt; 100")
        model = load_report_model(_dump(tmp_path, _report(weird)))
        assert not any(s.expression_name.startswith("Median") for s in model.summaries)
        assert any("not carried" in n for n in split_todos(model.issues)[MANUAL])


class TestTranslatorUnblocked:
    def test_bracketed_parameter_name_is_not_an_array(self):
        f = translate_formula(
            "Cond", '{?$[BOY_AB_FROMDATE]} = Date(1753,01,01)',
            field_types={})
        assert f.status != "manual", f.notes

    def test_trailing_semicolon_is_tolerated(self):
        f = translate_formula(
            "Cond", 'if ({O.TYPE}) = "Y" THEN false else True;',
            field_types={"TYPE": "StringField"})
        assert f.status != "manual", f.notes
        assert f.translation.startswith("=IF(")

    def test_a_real_array_subscript_still_blocks(self):
        f = translate_formula("Arr", '{O.TYPE}[1] = "Y"',
                              field_types={"TYPE": "StringField"})
        assert f.status == "manual"

    def test_two_statements_still_block(self):
        f = translate_formula(
            "Two", 'whileprintingrecords; numbervar test=1',
            field_types={})
        assert f.status == "manual"

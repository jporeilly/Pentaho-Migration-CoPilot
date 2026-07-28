"""Conditional section suppression when several Crystal sections merge into
one PRD band — the single biggest fidelity gap in the corpus (52 of 93
EnableSuppress conditions used to be dropped with a note).

Each Crystal section is now a COLLAPSING sub-band in the PRD layout, so the
suppress condition simply rides the section: a hidden section takes no height,
exactly like Crystal.
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


class TestSectionCondition:
    def test_condition_rides_the_section_for_its_sub_band(self, tmp_path):
        """Each Crystal section becomes a COLLAPSING PRD sub-band; the
        suppress condition belongs to the section, so the band takes no
        height when hidden - the collapse push-down-to-elements could not
        reproduce."""
        model = load_report_model(_dump(tmp_path, _report(SECTION_WITH_CONDITION)))
        first = next(s for s in model.sections if s.name == "DetailSection1")
        formula = dict(first.style_expressions)["visible"]
        # Crystal suppresses when TRUE; PRD's visible shows when TRUE — inverted
        assert "NOT" in formula.upper() and "[AMT]" in formula

    def test_the_sub_band_carries_the_condition_into_the_bundle(self, tmp_path):
        import zipfile

        from pentaho_migration.reports import write_prpt
        model = load_report_model(_dump(tmp_path, _report(SECTION_WITH_CONDITION)))
        out = tmp_path / "b.prpt"
        write_prpt(model, out)
        layout = zipfile.ZipFile(out).read("layout.xml").decode()
        assert 'band-styles layout="block"' in layout        # stacking parent
        band = layout.split('core:element-type="band"')[1]
        assert 'style-key="visible"' in layout

    def test_other_sections_elements_are_untouched(self, tmp_path):
        model = load_report_model(_dump(tmp_path, _report(SECTION_WITH_CONDITION)))
        second = next(s for s in model.sections if s.name == "DetailSection2")
        assert all("visible" not in dict(el.style_expressions)
                   for el in second.elements)

    def test_the_note_is_applied_not_manual(self, tmp_path):
        """This is work the pipeline DID - it must not land in the
        consultant's backlog."""
        model = load_report_model(_dump(tmp_path, _report(SECTION_WITH_CONDITION)))
        note = next(i for i in model.issues if "converted to a 'visible'" in i)
        assert split_todos([note])[APPLIED] == [note]

    def test_untranslatable_condition_stays_manual(self, tmp_path):
        weird = SECTION_WITH_CONDITION.replace(
            "{O.AMT} &gt; 100", "someUndeclaredVar &gt; 0")
        model = load_report_model(_dump(tmp_path, _report(weird)))
        first = next(s for s in model.sections if s.name == "DetailSection1")
        assert "visible" not in dict(first.style_expressions)
        manual = split_todos(model.issues)[MANUAL]
        assert any("not carried" in n for n in manual)

    def test_drill_down_level_folds_to_zero(self, tmp_path):
        """PRD has no drill-down, so a converted report is only ever the
        top-level view and Crystal's drill level is constantly 0. Folding it
        makes 'DrillDownGroupLevel <> 0' suppress exactly as Crystal's
        undrilled view does, instead of becoming a manual TODO."""
        drill = SECTION_WITH_CONDITION.replace(
            "{O.AMT} &gt; 100", "drilldowngrouplevel &lt;&gt; 0")
        model = load_report_model(_dump(tmp_path, _report(drill)))
        first = next(s for s in model.sections if s.name == "DetailSection1")
        assert dict(first.style_expressions)["visible"] == "=NOT(0 <> 0)"

    def test_page_number_becomes_a_declared_report_function(self, tmp_path):
        """Crystal writes special fields bare inside formulas. libformula has
        no PAGE(), so the condition references a PRD report function - which
        the bundle must actually declare, or the render fails."""
        import zipfile

        from pentaho_migration.reports import write_prpt

        paged = SECTION_WITH_CONDITION.replace(
            "{O.AMT} &gt; 100", "PageNumber = 1")
        model = load_report_model(_dump(tmp_path, _report(paged)))
        first = next(s for s in model.sections if s.name == "DetailSection1")
        assert dict(first.style_expressions)["visible"] == \
            "=NOT([CR_PageNumber] = 1)"
        out = tmp_path / "paged.prpt"
        write_prpt(model, out)
        with zipfile.ZipFile(out) as z:
            dd = z.read("datadefinition.xml").decode("utf-8")
        assert 'name="CR_PageNumber"' in dd
        assert "core.function.PageFunction" in dd

    def test_element_condition_is_independent_of_the_sections(self, tmp_path):
        """An element's own suppress condition stays on the element; the
        section's stays on the sub-band. Both apply at render - no merging."""
        both = SECTION_WITH_CONDITION.replace(
            '<TextObject Name="T1" Left="0" Top="0" Width="1440" Height="220">'
            "<Text>past due</Text></TextObject>",
            '<TextObject Name="T1" Left="0" Top="0" Width="1440" Height="220">'
            "<Text>past due</Text>"
            '<ObjectFormatConditionFormulas EnableSuppress="{O.TYPE} = &quot;X&quot;"/>'
            "</TextObject>")
        model = load_report_model(_dump(tmp_path, _report(both)))
        first = next(s for s in model.sections if s.name == "DetailSection1")
        assert "visible" in dict(first.style_expressions)
        assert "visible" in dict(first.elements[0].style_expressions)


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
        formula = dict(first.style_expressions)["visible"]
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


class TestBareSpecials:
    """RptToXml flattens a special field embedded in a text object to its bare
    name: "Page " + {PageNumber} arrives as the text "Page PageNumber" and
    used to print literally."""

    BAND = """\
    <Section Name="S1" Height="240"><ReportObjects>
      <TextObject Name="PgNum" Left="0" Top="0" Width="1440" Height="220">
        <Text>Page PageNumber</Text></TextObject>
      <TextObject Name="Printed" Left="0" Top="0" Width="1440" Height="220">
        <Text>Printed on PrintDate</Text></TextObject>
      <TextObject Name="Prose" Left="0" Top="0" Width="1440" Height="220">
        <Text>See the page number column</Text></TextObject>
    </ReportObjects></Section>"""

    def test_bare_specials_become_interpolations(self, tmp_path):
        model = load_report_model(_dump(tmp_path, _report(self.BAND)))
        els = {el.name: el for s in model.sections for el in s.elements}
        assert els["PgNum"].text_template == "Page $(PageofPages)"
        assert "$(report.date" in els["Printed"].text_template
        assert any("page n / m" in n for n in els["PgNum"].notes)

    def test_prose_containing_similar_words_is_untouched(self, tmp_path):
        model = load_report_model(_dump(tmp_path, _report(self.BAND)))
        els = {el.name: el for s in model.sections for el in s.elements}
        assert els["Prose"].text_template == ""   # stays a plain label

    def test_the_page_function_is_emitted_for_templates(self, tmp_path):
        import zipfile
        from pentaho_migration.reports import write_prpt
        model = load_report_model(_dump(tmp_path, _report(self.BAND)))
        out = tmp_path / "out.prpt"
        write_prpt(model, out)
        dd = zipfile.ZipFile(out).read("datadefinition.xml").decode()
        assert "PageOfPagesFunction" in dd, (
            "a template interpolating $(PageofPages) needs the function "
            "defined, or the message renders blank")


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


class TestZeroHeightSections:
    """A Crystal section can legitimately declare Height="0" - that is how a
    chart report collapses its per-row detail band so the whole report is one
    page. Forcing a 20pt floor turned 5000 invisible rows into 187 blank
    pages against the original's one; found by the release gate."""

    ZERO_DETAIL = """\
        <Section Name="DetailSection1" Height="0">
          <ReportObjects/>
        </Section>"""

    TALL_CONTENT = """\
        <Section Name="DetailSection1" Height="0">
          <ReportObjects>
            <FieldObject Name="F1" Left="0" Top="0" Width="1440"
                         Height="720" DataSource="{O.AMT}"/>
          </ReportObjects>
        </Section>"""

    def test_declared_zero_height_survives(self, tmp_path):
        model = load_report_model(_dump(tmp_path, _report(self.ZERO_DETAIL)))
        section = next(s for s in model.sections if s.name == "DetailSection1")
        assert section.height == 0.0

    def test_a_missing_height_still_defaults(self, tmp_path):
        """Absent is not the same as zero - an undeclared height has no
        Crystal intent behind it and keeps the readable default."""
        model = load_report_model(_dump(
            tmp_path, _report('<Section Name="DetailSection1"><ReportObjects/>'
                              "</Section>")))
        section = next(s for s in model.sections if s.name == "DetailSection1")
        assert section.height == 20.0

    def test_zero_height_band_still_fits_its_content(self, tmp_path):
        """Crystal's height wins for an EMPTY band, but a band whose objects
        reach past it must not clip them."""
        import zipfile

        from pentaho_migration.reports import write_prpt

        model = load_report_model(_dump(tmp_path, _report(self.TALL_CONTENT)))
        out = tmp_path / "tall.prpt"
        write_prpt(model, out)
        with zipfile.ZipFile(out) as z:
            layout = z.read("layout.xml").decode("utf-8")
        assert 'min-height="0"' not in layout

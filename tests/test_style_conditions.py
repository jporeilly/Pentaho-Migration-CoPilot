"""Conditional-format translation edge cases: crNoColor / DefaultAttribute
('keep the static style') and If-without-Else in condition formulas — all
become 2-arg IFs whose omitted branch falls back to the element's static
style (live-verified against the engine: the red branch fires, every other
row keeps its static ink)."""

import pytest

from pentaho_migration.reports.formula_translator import (
    TranslationError, translate_formula, translate_style_condition,
    translate_style_conditions)


def test_else_crnocolor_becomes_two_arg_if():
    key, expr = translate_style_condition(
        "Color", "If {C.STATUS} = 'Late' Then crRed Else crNoColor")
    assert key == "paint"
    assert expr == '=IF([STATUS] = "Late";"#ff0000")'


def test_else_defaultattribute_same_semantics():
    key, expr = translate_style_condition(
        "BackgroundColor", "If {C.AMT} > 100 Then crYellow Else DefaultAttribute")
    assert key == "background-color"
    assert expr == '=IF([AMT] > 100;"#ffff00")'


def test_then_keep_inverts_the_condition():
    _, expr = translate_style_condition(
        "Color", "If {C.OK} = 'Y' Then DefaultAttribute Else crRed")
    assert expr == '=IF(NOT([OK] = "Y");"#ff0000")'


def test_condition_without_else_keeps_static_style():
    _, expr = translate_style_condition(
        "Color", "If {C.STATUS} = 'Late' Then crRed")
    assert expr == '=IF([STATUS] = "Late";"#ff0000")'


def test_nested_else_keep_still_translates():
    _, expr = translate_style_condition(
        "Color",
        "If {C.S} = 'A' Then crRed Else If {C.S} = 'B' Then crBlue Else crNoColor")
    assert expr == '=IF([S] = "A";"#ff0000";IF([S] = "B";"#0000ff"))'


def test_bare_keep_or_unexpressible_position_stays_honest():
    with pytest.raises(TranslationError):
        translate_style_condition("Color", "crNoColor")


def test_regular_formulas_still_reject_defaultattribute():
    f = translate_formula("t", "If {C.A} > 1 Then DefaultAttribute Else 0")
    assert f.status == "manual"


class TestCorpusDrivenAttributes:
    """Attribute classes the corpus audit showed were being dropped. Each
    one is a Crystal behaviour that HAS a PRD equivalent, so leaving it as a
    manual TODO overstated the migration effort."""

    def test_font_style_fans_out_to_bold_and_italic(self):
        """Crystal returns one combined crBoldItalic; PRD carries bold and
        italic as two independent style keys, so the same formula has to be
        read once per key."""
        pairs = translate_style_conditions(
            "Style", "If {C.FLAG} = 'Y' Then crBoldItalic Else crRegular")
        assert dict(pairs) == {
            "font-bold": '=IF([FLAG] = "Y";TRUE();FALSE())',
            "font-italic": '=IF([FLAG] = "Y";TRUE();FALSE())',
        }

    def test_italic_only_does_not_turn_bold_on(self):
        pairs = dict(translate_style_conditions(
            "Style", "If {C.FLAG} = 'Y' Then crItalic Else crRegular"))
        assert pairs["font-bold"] == '=IF([FLAG] = "Y";FALSE();FALSE())'
        assert pairs["font-italic"] == '=IF([FLAG] = "Y";TRUE();FALSE())'

    def test_alignment_constants_map_to_prd_values(self):
        key, expr = translate_style_condition(
            "HorizontalAlignment",
            "If {C.FLAG} = 'Y' Then crRightAligned Else crLeftAligned")
        assert key == "alignment"
        assert expr == '=IF([FLAG] = "Y";"right";"left")'

    def test_literal_colour_components_fold_to_a_hex_value(self):
        _, expr = translate_style_condition(
            "BackgroundColor", "Color (255, 128, 0)")
        assert expr == '="#ff8000"'

    def test_colour_from_fields_stays_honest(self):
        """libformula has no decimal-to-hex conversion, so a colour computed
        at render time has no deterministic equivalent - emitting a wrong
        colour would be worse than saying so."""
        with pytest.raises(TranslationError):
            translate_style_condition(
                "BackgroundColor", "Color ({W.R}, {W.G}, {W.B})")

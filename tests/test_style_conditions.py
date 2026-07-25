"""Conditional-format translation edge cases: crNoColor / DefaultAttribute
('keep the static style') and If-without-Else in condition formulas — all
become 2-arg IFs whose omitted branch falls back to the element's static
style (live-verified against the engine: the red branch fires, every other
row keeps its static ink)."""

import pytest

from pentaho_migration.reports.formula_translator import (
    TranslationError, translate_formula, translate_style_condition)


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

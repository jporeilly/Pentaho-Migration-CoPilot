"""Crystal treats '%' in a number format as literal text; Java's DecimalFormat
(what PRD uses) treats it as a multiply-by-100 operator. A PercentOfSum that
already yields 36.16 with a "% #,##0.0" format therefore printed 3,616 until
the literal was quoted.
"""

from pentaho_migration.reports.prpt_render import _java_number_format


def test_a_literal_percent_is_quoted_so_the_value_is_not_scaled():
    assert _java_number_format("% #,##0.0") == "'%' #,##0.0"


def test_both_subpatterns_are_quoted():
    assert (_java_number_format("% #,##0.0;(% #,##0.0)")
            == "'%' #,##0.0;('%' #,##0.0)")


def test_a_plain_currency_format_is_untouched():
    assert _java_number_format("$ #,##0.00") == "$ #,##0.00"


def test_an_already_quoted_format_is_left_alone():
    assert _java_number_format("'%' #,##0.0") == "'%' #,##0.0"


def test_empty_is_safe():
    assert _java_number_format("") == ""

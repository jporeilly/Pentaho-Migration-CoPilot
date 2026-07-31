"""Old JFreeReport function/expression classes -> their PRD translation.

ONE table serves both definition dialects (the simple `<report>` parser
and the legacy-EXT `<report-definition>` parser) - the corpus2 sweep
found the same classes blocking reports in both, and a mapping fixed in
two places is a mapping that drifts.

The ground truth is the PRD engine itself: every fully-qualified class
in PORTABLE below is verified present in the local install's engine
jars by tests/test_jfreereport_functions.py (the same evidence standard
as the emitter-vs-shipped-samples harness). The old classes did not
die - they moved wholesale from ``org.jfree.report.*`` to
``org.pentaho.reporting.engine.classic.core.*`` with their subpackages
(``strings``, ``date``, ``modules.misc.beanshell``) preserved, so the
properties carry over verbatim, indexed names (``field[0]``) included.
"""

_CORE = 'org.pentaho.reporting.engine.classic.core.'

# short class name -> PRD fully-qualified class (jar-verified)
PORTABLE = {
    # element visibility / decoration drivers
    'ElementVisibilitySwitchFunction':
        _CORE + 'function.ElementVisibilitySwitchFunction',
    'ShowElementIfDataAvailableExpression':
        _CORE + 'function.ShowElementIfDataAvailableExpression',
    'HideElementIfDataAvailableExpression':
        _CORE + 'function.HideElementIfDataAvailableExpression',
    'ItemHideFunction': _CORE + 'function.ItemHideFunction',
    'ElementColorFunction': _CORE + 'function.ElementColorFunction',
    'CreateHyperLinksFunction': _CORE + 'function.CreateHyperLinksFunction',
    'CreateGroupAnchorsFunction':
        _CORE + 'function.CreateGroupAnchorsFunction',
    # computed values
    'AverageExpression': _CORE + 'function.AverageExpression',
    'TextFormatExpression': _CORE + 'function.TextFormatExpression',
    'DateExpression': _CORE + 'function.date.DateExpression',
    'ToUpperCaseStringExpression':
        _CORE + 'function.strings.ToUpperCaseStringExpression',
    'ToLowerCaseStringExpression':
        _CORE + 'function.strings.ToLowerCaseStringExpression',
    'SubStringExpression': _CORE + 'function.strings.SubStringExpression',
    'MessageFormatExpression':
        _CORE + 'function.strings.MessageFormatExpression',
    # scripted: PRD ships the same BeanShell interpreter (bsh jar in lib)
    'BSHExpression': _CORE + 'modules.misc.beanshell.BSHExpression',
}

# property names that reference layout ELEMENTS by name - the writer
# must emit core:name on those elements or the ported function finds
# nothing to act on
TARGET_PROPS = ('element',)

# aggregate function classes -> (operation, running). The Item* family
# is a RUNNING value (row-by-row); Group*/TotalGroup* are group totals.
AGGREGATES = {
    'GroupCountFunction': ('Count', False),
    'ItemCountFunction': ('Count', True),
    'GroupSumFunction': ('Sum', False),
    'ItemSumFunction': ('Sum', True),
    'TotalGroupSumFunction': ('Sum', False),
    'ItemAvgFunction': ('Average', True),
    'ItemMinFunction': ('Minimum', True),
    'ItemMaxFunction': ('Maximum', True),
}

# classes the writer re-creates itself - elements bound to the function
# name become PRD special fields instead
SPECIALS = {
    'PageOfPagesFunction': 'pagenofm',
}

# per-class flavour for the conversion note, so the reviewer knows WHAT
# behaviour to verify rather than just that a class moved packages
_NOTE_FLAVOUR = {
    'ElementVisibilitySwitchFunction':
        "it toggles element '{element}' per row (banded shading) - "
        'verify the shading',
    'ShowElementIfDataAvailableExpression':
        "it shows element '{element}' only when the query returns rows "
        '- verify the no-data state',
    'HideElementIfDataAvailableExpression':
        "it hides element '{element}' when the query returns rows (the "
        "classic no-data banner) - verify the no-data state",
    'ItemHideFunction':
        "it suppresses repeated values of '{field}' on element "
        "'{element}' - verify the first row of each group still prints",
    'ElementColorFunction':
        "it colours element '{element}' by boolean '{field}' "
        '({colorTrue}/{colorFalse})',
    'CreateHyperLinksFunction':
        "it links element '{element}' to the URL in '{field}' - "
        'hyperlinks show in HTML/PDF output, not on paper',
    'BSHExpression':
        'a BeanShell SCRIPT carried verbatim (PRD ships the same '
        'interpreter, bsh 2.x in lib) - review the script logic',
}


def targets(cls_short, props):
    """Element names this function acts on, for core:name emission."""
    if cls_short not in PORTABLE:
        return []
    return [props[p] for p in TARGET_PROPS if props.get(p)]


def port_note(name, cls_short, props):
    flavour = _NOTE_FLAVOUR.get(cls_short)
    note = ("report function '{}' ({}) ported unchanged - PRD ships the "
            'same class'.format(name, cls_short))
    if flavour:
        class _Blank(dict):
            def __missing__(self, key):
                return '?'
        note += '; ' + flavour.format_map(_Blank(props))
    return note


def translate(cls_short, name, props):
    """One old function -> its PRD decision:

    ``('aggregate', (operation, running))`` - map to a Summary
    ``('special', column)``  - elements bound to it become special fields
    ``('port', fqcn)``       - emit verbatim under the PRD class name
    ``(None, None)``         - no mapping; the caller keeps its honest note
    """
    if cls_short in AGGREGATES:
        return 'aggregate', AGGREGATES[cls_short]
    if cls_short in SPECIALS:
        return 'special', SPECIALS[cls_short]
    if cls_short in PORTABLE:
        return 'port', PORTABLE[cls_short]
    return None, None

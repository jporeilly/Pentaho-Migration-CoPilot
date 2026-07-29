"""Translate a narrow family of Crystal formulas to a SQL expression.

There is exactly one place a Crystal formula must become a real query
column rather than a PRD expression: a cross-tab pivots over the columns of
its result set, so a dimension COMPUTED in the report has nothing to spread
over unless the database supplies it. The whole SAP BOE income-statement
family pivots its columns on {@date} = cdate(Year, Month, 1), a date built
from two columns - and a PRD expression there crashes the render (no
itemband to read the value's format from), while leaving it out renders the
cross-tab empty.

Deliberately narrow. Only the date-construction family is handled, because
that is what cross-tab dimensions actually use across the corpus, and a
wrong guess here ships a query that RUNS but returns the wrong columns -
worse than an honest note. Anything outside the family returns None and the
caller falls back to a manual TODO.

Dialect matters: STR_TO_DATE is MySQL. Only dialects with a known-correct
expression return SQL; the rest return None. The caller emits a note about
the assumption even for the dialect it does support, because the same .prpt
may be pointed at another database later.
"""

import re

# {table.column} or a bare {column}
_FIELD = re.compile(r"^\{(?:[^.}]+\.)?([^.}]+)\}$")
_INT = re.compile(r"^-?\d+$")
# Crystal constructors that build a date from year, month, day (3 args).
# CDate/Date are dual-form - one argument parses a string instead - so the
# three-argument shape is what identifies construction.
_DATE_CTORS = ("cdate", "date", "dateserial")


def _split_args(inner: str) -> list:
    """Split a call's argument list on TOP-LEVEL commas."""
    args, depth, cur = [], 0, ""
    for ch in inner:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            args.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        args.append(cur.strip())
    return args


def _operand(arg: str, tables: dict):
    """A field reference or integer literal as SQL, else None.

    A field is qualified with its owning table where one claims it, matching
    the naming the generated SELECT already uses; an unqualified column that
    no table claims is left bare rather than guessed at."""
    m = _FIELD.match(arg.strip())
    if m:
        col = m.group(1)
        table = next((t for t, fs in tables.items() if col in fs), None)
        return f"{table}.{col}" if table else col
    if _INT.match(arg.strip()):
        return arg.strip()
    return None


def formula_to_sql(text: str, tables: dict, dialect: str = "mysql"):
    """A SQL expression equivalent to the Crystal formula `text`, or None
    when it is outside the supported family or the dialect is unknown.

    `tables` is model.tables (alias -> {column: type})."""
    s = (text or "").strip()
    m = re.match(r"(?i)^([a-z]+)\s*\((.*)\)$", s, re.S)
    if not m:
        return None
    if m.group(1).lower() not in _DATE_CTORS:
        return None
    args = _split_args(m.group(2))
    if len(args) != 3:                        # a date FROM PARTS, not a parse
        return None
    parts = [_operand(a, tables) for a in args]
    if any(p is None for p in parts):
        return None
    year, month, day = parts
    if dialect == "mysql":
        # %c / %e accept an unpadded month and day, so 2016-1-1 parses as it
        # stands without zero-padding the concatenated pieces
        return (f"STR_TO_DATE(CONCAT_WS('-', {year}, {month}, {day}), "
                "'%Y-%c-%e')")
    return None

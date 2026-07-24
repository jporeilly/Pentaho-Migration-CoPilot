"""Fold simple Crystal record-selection formulas into the SQL WHERE clause.

Crystal's record selection is the report's row filter; PRD has no equivalent
concept — the query itself must filter. For the common shape (a conjunction
of simple comparisons against parameters or literals) the fold is fully
deterministic, which finally makes converted parameter prompts *work*:
changing the prompt re-runs the query and filters the report.

Anything more complex (parentheses, OR, functions, LIKE, date ranges) stays
manual and keeps its conversion-report entry — never guessed.
"""

import re

# {TABLE.FIELD} op RHS, where RHS is {?Param}, a number, or a quoted string
_CLAUSE_RE = re.compile(
    r"^\{(?P<table>\w+)\.(?P<field>\w+)\}\s*"
    r"(?P<op><>|<=|>=|=|<|>)\s*"
    r"(?P<rhs>\{\?\w+\}|-?\d+(?:\.\d+)?|'[^']*'|\"[^\"]*\")$")

_PARAM_RE = re.compile(r"^\{\?(\w+)\}$")


def _select_alias_map(sql: str) -> dict:
    """Map SELECT-list aliases to their source expressions. Crystal Command
    reports reference fields as {Command.ALIAS}, but SQL WHERE clauses cannot
    use SELECT aliases - the filter must target the source column."""
    m = re.search(r"\bSELECT\b(.*?)\bFROM\b", sql, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return {}
    aliases = {}
    for expr, alias in re.findall(
            r'([\w.]+)\s+AS\s+"?(\w+)"?', m.group(1), flags=re.IGNORECASE):
        aliases[alias.upper()] = expr
    return aliases


def _sql_column(table: str, field: str, alias_map: dict) -> str:
    if table.lower() == "command":
        src = alias_map.get(field.upper())
        if src:
            return src
        return field  # bare column - best effort for unaliased Command fields
    return f"{table}.{field}"


def _sql_is_simple(sql: str) -> bool:
    upper = sql.upper()
    return (";" not in sql
            and "DECLARE" not in upper
            and upper.count("SELECT") == 1
            and "UNION" not in upper
            and "GROUP BY" not in upper)


def try_fold_record_selection(model) -> bool:
    """Attempt the fold. On success: model.sql gains the WHERE clause,
    model.record_selection_folded is set, and True is returned. On failure
    the model is untouched (the formula stays a manual work item)."""
    formula = (model.record_selection or "").strip()
    if not formula or not _sql_is_simple(model.sql):
        return False
    if "(" in formula or ")" in formula:
        return False

    alias_map = _select_alias_map(model.sql)
    clauses = []
    for part in re.split(r"\s+and\s+", formula, flags=re.IGNORECASE):
        m = _CLAUSE_RE.match(part.strip())
        if not m:
            return False  # OR / functions / unsupported shape -> stay manual
        table, field, op, rhs = m.group("table", "field", "op", "rhs")
        column = _sql_column(table, field, alias_map)
        pm = _PARAM_RE.match(rhs)
        if pm:
            name = pm.group(1)
            prm = next((p for p in model.parameters if p.name == name), None)
            if prm is None:
                return False
            if prm.multi_value:
                if op != "=":
                    return False
                clauses.append(f"{column} IN (${{{name}}})")
            else:
                clauses.append(f"{column} {op} ${{{name}}}")
        else:
            if rhs.startswith('"'):
                rhs = "'" + rhs[1:-1].replace("'", "''") + "'"
            clauses.append(f"{column} {op} {rhs}")

    if not clauses:
        return False
    where = " AND ".join(clauses)

    # insert before the final top-level ORDER BY (or append)
    m = list(re.finditer(r"\bORDER\s+BY\b", model.sql, flags=re.IGNORECASE))
    kw = "AND" if re.search(r"\bWHERE\b", model.sql, flags=re.IGNORECASE) else "WHERE"
    if m:
        idx = m[-1].start()
        model.sql = f"{model.sql[:idx].rstrip()}\n{kw} {where}\n{model.sql[idx:]}"
    else:
        model.sql = f"{model.sql.rstrip()}\n{kw} {where}"
    model.record_selection_folded = True
    return True

"""Translate Crystal Reports formula syntax to Pentaho OpenFormula (libformula).

Strategy (mirrors the Migration Copilot philosophy): translate the
deterministic 80% mechanically, and *honestly flag* everything else as
manual work rather than guessing.

Statuses:
  auto   - fully translated, no caveats
  review - translated, but a mapping deserves a human glance (noted)
  manual - not translatable mechanically; original text preserved

Hard blockers (-> manual): variable declarations (shared/global/local,
xxxVar), assignments (:=), multi-statement bodies, evaluation-time
directives (WhilePrintingRecords etc.), control flow (Select/For/While),
and array subscripts.
"""

import re

from .model import Formula


class TranslationError(Exception):
    pass


BLOCKER_PATTERNS = [
    (r"(?i)\b(shared|global|local)\b", "variable scope declaration"),
    (r"(?i)\b(string|number|date|time|datetime|currency|boolean)var\b", "variable declaration"),
    (r":=", "variable assignment"),
    (r"(?i)\bwhile(printing|reading)records\b", "evaluation-time directive"),
    (r"(?i)\bevaluateafter\b", "evaluation-time directive"),
    (r"(?i)\bselect\s", "Select Case control flow"),
    (r"(?i)\bfor\s+\w+\s*:?=", "For loop"),
    (r"(?i)\bdo\s+while\b|\bwhile\s.*\bdo\b", "While loop"),
    (r"\[", "array subscript / array literal"),
]

# Crystal function -> (OpenFormula function, note or None, arg transformer or None)
FUNC_MAP = {
    "totext":      ("TEXT", "ToText mapped to TEXT(); verify format arguments", None),
    "cstr":        ("TEXT", "CStr mapped to TEXT(); verify format arguments", None),
    "tonumber":    ("VALUE", None, None),
    "uppercase":   ("UPPER", None, None),
    "ucase":       ("UPPER", None, None),
    "lowercase":   ("LOWER", None, None),
    "lcase":       ("LOWER", None, None),
    "propercase":  ("PROPER", None, None),
    "trim":        ("TRIM", None, None),
    "trimleft":    ("TRIM", "TrimLeft approximated with TRIM (trims both ends)", None),
    "trimright":   ("TRIM", "TrimRight approximated with TRIM (trims both ends)", None),
    "left":        ("LEFT", None, None),
    "right":       ("RIGHT", None, None),
    "mid":         ("MID", None, None),
    "length":      ("LEN", None, None),
    "len":         ("LEN", None, None),
    "instr":       ("FIND", "InStr(haystack, needle) became FIND(needle; haystack) - args swapped", lambda a: [a[1], a[0]] + a[2:] if len(a) >= 2 else a),
    "replace":     ("SUBSTITUTE", None, None),
    "isnull":      ("ISBLANK", "Crystal IsNull became ISBLANK; NULL semantics differ from empty", None),
    "abs":         ("ABS", None, None),
    "round":       ("ROUND", None, None),
    "int":         ("INT", None, None),
    "truncate":    ("TRUNC", None, None),
    "sqr":         ("SQRT", None, None),
    "exp":         ("EXP", None, None),
    "log":         ("LN", "Crystal Log is natural log -> LN", None),
    "minimum":     ("MIN", None, None),
    "maximum":     ("MAX", None, None),
    "year":        ("YEAR", None, None),
    "month":       ("MONTH", None, None),
    "day":         ("DAY", None, None),
    "hour":        ("HOUR", None, None),
    "minute":      ("MINUTE", None, None),
    "second":      ("SECOND", None, None),
    "date":        ("DATE", None, None),
    "cdate":       ("DATEVALUE", "CDate mapped to DATEVALUE; verify input format", None),
    "datevalue":   ("DATEVALUE", None, None),
    "weekday":     ("WEEKDAY", "Verify weekday numbering convention", None),
    "iif":         ("IF", None, None),
    "chr":         ("CHAR", "Chr mapped to CHAR - verify code page for non-ASCII codes", None),
    "chrw":        ("CHAR", "ChrW mapped to CHAR", None),
    "asc":         ("CODE", "Asc mapped to CODE", None),
}

NOARG_MAP = {
    "currentdate": "TODAY()",
    "today": "TODAY()",
    "currentdatetime": "NOW()",
    "now": "NOW()",
    "true": "TRUE()",
    "false": "FALSE()",
    "printdate": "TODAY()",
}

KEYWORDS = {"if", "then", "else", "and", "or", "not", "mod", "in", "to"}

TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*)
  | (?P<str>"(?:[^"]|"")*"|'(?:[^']|'')*')
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<field>\{[^}]+\})
  | (?P<op><=|>=|<>|[=<>+\-*/&%(),:])
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
""", re.VERBOSE)


def _tokenize(text):
    tokens, pos = [], 0
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise TranslationError(f"unrecognized syntax at: {text[pos:pos + 20]!r}")
        pos = m.end()
        if m.lastgroup in ("ws", "comment"):
            continue
        tokens.append((m.lastgroup, m.group()))
    return tokens


def _field_to_openformula(raw):
    inner = raw[1:-1]
    if inner[0] in "@?#":
        inner = inner[1:]
    else:
        inner = inner.split(".")[-1]
    return f"[{inner}]"


def _string_to_openformula(raw):
    if raw[0] == '"':
        return raw
    body = raw[1:-1].replace("''", "'").replace('"', '""')
    return f'"{body}"'


STRING_TYPES = {"StringField", "MemoField", "PersistentMemoField"}
_FIELD_REF_ONLY = re.compile(r"^\[(\w+)\]$")


class _Parser:
    """Recursive-descent translator emitting OpenFormula text."""

    def __init__(self, tokens, field_types=None):
        self.tokens = tokens
        self.pos = 0
        self.notes = []
        self.field_types = field_types or {}

    def _is_stringish(self, operand):
        """True when an emitted operand is knowably a string: a literal at
        either end (covers concat chains), or a field reference whose
        database type says so."""
        s = operand.strip()
        if s.startswith('"') or s.endswith('"'):
            return True
        m = _FIELD_REF_ONLY.match(s)
        return bool(m) and self.field_types.get(m.group(1)) in STRING_TYPES

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def next(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def _is_kw(self, tok, word):
        return tok[0] == "ident" and tok[1].lower() == word

    def parse(self):
        out = self.expr()
        if self.pos < len(self.tokens):
            raise TranslationError(f"unexpected trailing tokens: {self.tokens[self.pos:][:3]}")
        return out

    def expr(self):
        return self.or_expr()

    def or_expr(self):
        parts = [self.and_expr()]
        while self._is_kw(self.peek(), "or"):
            self.next()
            parts.append(self.and_expr())
        return parts[0] if len(parts) == 1 else "OR(" + ";".join(parts) + ")"

    def and_expr(self):
        parts = [self.not_expr()]
        while self._is_kw(self.peek(), "and"):
            self.next()
            parts.append(self.not_expr())
        return parts[0] if len(parts) == 1 else "AND(" + ";".join(parts) + ")"

    def not_expr(self):
        if self._is_kw(self.peek(), "not"):
            self.next()
            return "NOT(" + self.not_expr() + ")"
        return self.cmp_expr()

    def cmp_expr(self):
        left = self.add_expr()
        kind, val = self.peek()
        if kind == "op" and val in ("=", "<>", "<", ">", "<=", ">="):
            self.next()
            right = self.add_expr()
            return f"{left} {val} {right}"
        if self._is_kw(self.peek(), "in"):
            raise TranslationError("'in' range/set test has no direct OpenFormula equivalent")
        return left

    def add_expr(self):
        out = self.mul_expr()
        while True:
            kind, val = self.peek()
            if kind == "op" and val in ("+", "-", "&"):
                self.next()
                right = self.mul_expr()
                # string concatenation: Crystal '+' -> OpenFormula '&'.
                # OpenFormula '+' fails on strings at runtime, so use the
                # database field types, not just literals, to decide.
                if val == "+" and (self._is_stringish(out) or self._is_stringish(right)):
                    val = "&"
                out = f"{out} {val} {right}"
            else:
                return out

    def mul_expr(self):
        # note: '%' is deliberately NOT an operator here — Crystal has no
        # binary %, and OpenFormula's % is a postfix percent (divide by 100),
        # so passing it through would silently change semantics
        out = self.unary()
        while True:
            kind, val = self.peek()
            if kind == "op" and val in ("*", "/"):
                self.next()
                out = f"{out} {val} {self.unary()}"
            elif self._is_kw(self.peek(), "mod"):
                self.next()
                out = f"MOD({out};{self.unary()})"
            else:
                return out

    def unary(self):
        kind, val = self.peek()
        if kind == "op" and val == "-":
            self.next()
            return "-" + self.unary()
        return self.primary()

    def primary(self):
        kind, val = self.next()
        if kind is None:
            raise TranslationError("unexpected end of formula")
        if kind == "num":
            return val
        if kind == "str":
            return _string_to_openformula(val)
        if kind == "field":
            return _field_to_openformula(val)
        if kind == "op" and val == "(":
            inner = self.expr()
            self._expect_op(")")
            return f"({inner})"
        if kind == "ident":
            low = val.lower()
            if low == "if":
                return self.if_expr()
            nk, nv = self.peek()
            if nk == "op" and nv == "(":
                return self.func_call(low, val)
            if low in NOARG_MAP:
                return NOARG_MAP[low]
            if low in KEYWORDS:
                raise TranslationError(f"unexpected keyword {val!r}")
            raise TranslationError(f"unknown identifier {val!r} (undeclared variable?)")
        raise TranslationError(f"unexpected token {val!r}")

    def if_expr(self):
        cond = self.expr()
        if not self._is_kw(self.peek(), "then"):
            raise TranslationError("If without Then")
        self.next()
        then_val = self.expr()
        if self._is_kw(self.peek(), "else"):
            self.next()
            else_val = self.expr()
        else:
            else_val = '""' if then_val.lstrip().startswith('"') else "0"
            self.notes.append("Crystal If without Else: default branch emitted "
                              f"({else_val}) to match Crystal's implicit default")
        return f"IF({cond};{then_val};{else_val})"

    def func_call(self, low, original):
        self._expect_op("(")
        args = []
        if not (self.peek()[0] == "op" and self.peek()[1] == ")"):
            args.append(self.expr())
            while self.peek()[0] == "op" and self.peek()[1] == ",":
                self.next()
                args.append(self.expr())
        self._expect_op(")")
        if low in ("sum", "count", "average", "maximum", "minimum", "distinctcount") and args and args[0].startswith("["):
            raise TranslationError(
                f"aggregate {original}() must become a report function "
                "(ItemSumFunction etc.), not an inline formula")
        if low == "switch":
            return self._switch(args)
        if low == "datediff":
            return self._datediff(args)
        if low not in FUNC_MAP:
            raise TranslationError(f"no OpenFormula mapping for function {original}()")
        target, note, arg_fn = FUNC_MAP[low]
        if note:
            self.notes.append(note)
        if arg_fn:
            args = arg_fn(args)
        return f"{target}({';'.join(args)})"

    def _switch(self, args):
        """Crystal Switch(c1, v1, c2, v2, ...) -> nested IF. Crystal returns
        Null when nothing matches; NA() is the faithful equivalent."""
        if len(args) < 2:
            raise TranslationError("Switch() needs at least one condition/value pair")
        if len(args) % 2 == 1:
            raise TranslationError("Switch() with an odd argument count "
                                   "(condition without value)")
        out = "NA()"
        self.notes.append("Switch with no matching condition returns NA() "
                          "(Crystal returns Null) - verify downstream handling")
        for i in range(len(args) - 2, -1, -2):
            out = f"IF({args[i]};{args[i + 1]};{out})"
        return out

    DATEDIFF_INTERVALS = {'"d"': '"d"', '"m"': '"m"', '"yyyy"': '"y"'}

    def _datediff(self, args):
        """Crystal DateDiff("d", start, end) -> DATEDIF(start; end; unit)."""
        if len(args) != 3:
            raise TranslationError("DateDiff() with other than 3 arguments")
        unit = self.DATEDIFF_INTERVALS.get(args[0].strip().lower())
        if unit is None:
            raise TranslationError(
                f"DateDiff interval {args[0]} has no DATEDIF equivalent "
                "(only d/m/yyyy map)")
        self.notes.append("DateDiff mapped to DATEDIF - verify boundary "
                          "semantics (Crystal counts interval crossings)")
        return f"DATEDIF({args[1]};{args[2]};{unit})"

    def _expect_op(self, symbol):
        kind, val = self.next()
        if kind != "op" or val != symbol:
            raise TranslationError(f"expected {symbol!r}, found {val!r}")


def _parse_slice(tokens, field_types, notes):
    p = _Parser(tokens, field_types=field_types)
    out = p.parse()
    notes.extend(p.notes)
    return out


def _split_on_op(tokens, symbol):
    """Split a token list on a top-level operator (paren-depth 0)."""
    parts, current, depth = [], [], 0
    for tok in tokens:
        kind, val = tok
        if kind == "op" and val == "(":
            depth += 1
        elif kind == "op" and val == ")":
            depth -= 1
        if kind == "op" and val == symbol and depth == 0:
            parts.append(current)
            current = []
        else:
            current.append(tok)
    parts.append(current)
    return parts


def translate_select_case(text, field_types=None):
    """Crystal `Select {x} Case v1: r1 Case v2, v3: r2 Default: rd` ->
    nested IF(...). Returns (openformula, notes); raises TranslationError on
    shapes that do not map (ranges `1 To 5`, `Is < x`, missing parts)."""
    notes = []
    tokens = _tokenize(re.sub(r"//[^\n]*", "", text))
    if not tokens or not (tokens[0][0] == "ident" and tokens[0][1].lower() == "select"):
        raise TranslationError("not a Select Case formula")

    # split into: selector, then (case ...)+, optional (default ...)
    segments, current, seg_kind, depth = [], [], "select", 0
    for tok in tokens[1:]:
        kind, val = tok
        if kind == "op" and val == "(":
            depth += 1
        elif kind == "op" and val == ")":
            depth -= 1
        if kind == "ident" and depth == 0 and val.lower() in ("case", "default"):
            segments.append((seg_kind, current))
            current, seg_kind = [], val.lower()
        else:
            current.append(tok)
    segments.append((seg_kind, current))

    selector_tokens = segments[0][1]
    if not selector_tokens:
        raise TranslationError("Select without a selector expression")
    selector = _parse_slice(selector_tokens, field_types, notes)

    branches, default = [], None
    for seg_kind, seg in segments[1:]:
        if seg_kind == "default":
            if not seg or seg[0] != ("op", ":"):
                raise TranslationError("Default without ':'")
            default = _parse_slice(seg[1:], field_types, notes)
            continue
        halves = _split_on_op(seg, ":")
        if len(halves) != 2:
            raise TranslationError("Case branch is not 'values : result'")
        value_tokens, result_tokens = halves
        for kind, val in value_tokens:
            if kind == "ident" and val.lower() in ("to", "is"):
                raise TranslationError(
                    f"Case range ({val} ...) has no direct IF() equivalent")
        conditions = []
        for value in _split_on_op(value_tokens, ","):
            if not value:
                raise TranslationError("empty Case value")
            conditions.append(f"{selector} = {_parse_slice(value, field_types, notes)}")
        cond = conditions[0] if len(conditions) == 1 else "OR(" + ";".join(conditions) + ")"
        branches.append((cond, _parse_slice(result_tokens, field_types, notes)))

    if not branches:
        raise TranslationError("Select without any Case branch")
    if default is None:
        default = "NA()"
        notes.append("Select Case without Default returns NA() when nothing "
                     "matches (Crystal returns Null) - verify downstream handling")
    out = default
    for cond, result in reversed(branches):
        out = f"IF({cond};{result};{out})"
    notes.append("Select Case rewritten as nested IF(...) - verify branch "
                 "order and comparison semantics")
    return out, notes


# the classic Crystal running-total idiom:
#   [WhilePrintingRecords;] [Shared|Global|Local] NumberVar X; X := X + <term>; X
_RUNNING_TOTAL_RE = re.compile(
    r"^(?:whileprintingrecords\s*;\s*)?"
    r"(?:shared|global|local)?\s*numbervar\s+(?P<var>\w+)\s*;\s*"
    r"(?P=var)\s*:=\s*(?P=var)\s*\+\s*(?P<term>\{[^}]+\}|1)\s*;\s*"
    r"(?P=var)\s*;?\s*$",
    re.IGNORECASE)


# a formula whose entire body is one aggregate call: Sum({T.F}) or
# Sum({T.F}, {T.Group}) - Crystal grand/group totals
_WHOLE_AGGREGATE_RE = re.compile(
    r"^(?P<op>sum|count|maximum|minimum)\s*\(\s*\{(?P<field>[^}]+)\}\s*"
    r"(?:,\s*\{(?P<group>[^}]+)\}\s*)?\)$",
    re.IGNORECASE)

_FUNC_PKG = "org.pentaho.reporting.engine.classic.core.function."
_AGGREGATE_CLASS = {              # classes verified against PRD classic-core
    "sum": _FUNC_PKG + "TotalGroupSumFunction",
    "count": _FUNC_PKG + "TotalGroupCountFunction",
    "maximum": _FUNC_PKG + "TotalItemMaxFunction",
    "minimum": _FUNC_PKG + "TotalItemMinFunction",
}


def _bare_column(field_ref):
    return field_ref.strip("{}").split(".")[-1].lstrip("@?#")


def detect_rewrite(text):
    """(function_class, field, group, why) when a blocked Crystal idiom maps
    mechanically onto a native PRD report function; None otherwise.

    Recognized today: the running-total variable idiom (-> ItemSumFunction /
    ItemCountFunction) and whole-formula aggregates like Sum({T.F}, {T.G})
    (-> Total*Function). Same principle extends to further idioms over time:
    generate the function for review instead of only advising."""
    normalized = re.sub(r"//[^\n]*", "", text)
    normalized = " ".join(normalized.split())

    m = _RUNNING_TOTAL_RE.match(normalized)
    if m:
        term = m.group("term")
        if term == "1":
            return (_FUNC_PKG + "ItemCountFunction", "", "", "running-count variable")
        return (_FUNC_PKG + "ItemSumFunction", _bare_column(term), "",
                "running-total variable")

    m = _WHOLE_AGGREGATE_RE.match(normalized)
    if m:
        cls = _AGGREGATE_CLASS[m.group("op").lower()]
        group = _bare_column("{%s}" % m.group("group")) if m.group("group") else ""
        return (cls, _bare_column("{%s}" % m.group("field")), group,
                f"{m.group('op')} aggregate")
    return None


def translate_formula(name, text, field_types=None):
    """Translate one Crystal formula. Returns a Formula with status filled in.
    `field_types` (bare column -> Crystal ValueType) enables type-aware
    decisions like string '+' -> '&'."""
    f = Formula(name=name, text=text)
    rewrite = detect_rewrite(text)
    if rewrite is not None:
        f.rewrite_class, f.rewrite_field, f.rewrite_group, why = rewrite
        f.status = "review"
        kind = f.rewrite_class.rsplit(".", 1)[-1]
        note = (f"{why} rewritten as a PRD {kind}"
                + (f" over [{f.rewrite_field}]" if f.rewrite_field else "")
                + (f" grouped by [{f.rewrite_group}]" if f.rewrite_group else ""))
        if "running" in why:
            note += (" - verify reset semantics (Crystal shared variables persist "
                     "across groups and subreports; add a group to the function "
                     "to reset per group)")
        else:
            note += " - verify scope matches the Crystal placement"
        f.notes.append(note)
        return f
    stripped = re.sub(r"//[^\n]*", "", text)
    if re.match(r"(?i)\s*select\b", stripped):
        # Select Case maps mechanically onto nested IF() - generate the PRD
        # formula for review instead of flagging it manual
        try:
            translation, notes = translate_select_case(text, field_types)
            f.translation = "=" + translation
            f.notes = notes
            f.status = "review"
        except TranslationError as e:
            f.status = "manual"
            f.notes.append(f"Select Case not mechanically translatable ({e}). "
                           "Rebuild by hand in PRD (often as a report function "
                           "or a pre-computed SQL column).")
        return f
    for pattern, why in BLOCKER_PATTERNS:
        if re.search(pattern, stripped):
            f.status = "manual"
            f.notes.append(f"Blocked: {why}. Rebuild by hand in PRD "
                           "(often as a report function or a pre-computed SQL column).")
            return f
    try:
        parser = _Parser(_tokenize(text), field_types=field_types)
        f.translation = "=" + parser.parse()
        f.notes = parser.notes
        f.status = "review" if parser.notes else "auto"
    except TranslationError as e:
        f.status = "manual"
        f.notes.append(f"Not mechanically translatable: {e}")
    return f


def translate_all(model):
    for name, formula in model.formulas.items():
        model.formulas[name] = translate_formula(
            name, formula.text, field_types=model.field_types)
    return model

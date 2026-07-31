"""A safe interpreter for the JavaScript subset xaction sequences use.

The platform ran a script's assignments top to bottom and substituted
the outputs into queries, titles and email bodies. The corpus (196
scripts across two estates) clusters into a handful of shapes, and most
of them are deterministic given the sequence's own input defaults:
literal assignments, string concatenation (`+`, `+=`), arithmetic, and
`if/else` defaulting (`if (x == "default" || null == x) ...`).

This evaluates exactly that subset with **prefix semantics**: statements
run in order and evaluation STOPS at the first construct outside the
subset (a method call like ``dsResult.getValueAt``, a loop, ``new``).
Outputs assigned before the stop are exact - the platform executed the
same prefix the same way - and the stopping statement is reported so the
caller can say honestly why the rest stayed manual.

JavaScript semantics that matter and are honoured: ``+`` concatenates
when either side is a string (``(YEAR - 1) + ""`` -> ``"2003"``),
``==`` compares loosely enough for the corpus (string/number/null),
an undefined input reads as ``null``, numbers print without a trailing
``.0``. No attribute access, no calls, no loops, no ``new`` - by design.
"""

import re


class _Stop(Exception):
    """Raised at the first statement outside the subset. Carries the
    offending source fragment for the caller's honest note."""

    def __init__(self, fragment):
        super().__init__(fragment)
        self.fragment = fragment


_TOKEN = re.compile(r"""
    \s*(?:
      (?P<comment>//[^\n]*|/\*.*?\*/)
    | (?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
    | (?P<number>\d+(?:\.\d+)?)
    | (?P<name>[A-Za-z_$][\w$]*)
    | (?P<op>\+=|-=|==|!=|<=|>=|&&|\|\||[+\-*/%<>=!(){};,.\[\]])
    )""", re.VERBOSE | re.DOTALL)


def _tokenize(script):
    tokens = []
    pos = 0
    while pos < len(script):
        m = _TOKEN.match(script, pos)
        if not m:
            if script[pos:].strip() == "":
                break
            raise _Stop(script[pos:pos + 30])
        pos = m.end()
        if m.lastgroup == "comment":
            continue
        tokens.append((m.lastgroup, m.group(m.lastgroup)))
    return tokens


_KEYWORD_STOPS = {"for", "while", "do", "function", "new", "return",
                  "switch", "try", "throw", "typeof", "delete"}


class _Interp:
    def __init__(self, tokens, scope):
        self.toks = tokens
        self.i = 0
        self.scope = scope

    # ---- token helpers ---------------------------------------------------
    def peek(self, offset=0):
        j = self.i + offset
        return self.toks[j] if j < len(self.toks) else (None, None)

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, value):
        kind, val = self.next()
        if val != value:
            raise _Stop(f"expected {value!r}, saw {val!r}")

    def _context(self):
        frag = " ".join(v for _k, v in self.toks[self.i:self.i + 8])
        return frag or "<end>"

    # ---- statements ------------------------------------------------------
    def run(self):
        while self.peek()[0] is not None:
            self.statement()

    def statement(self):
        kind, val = self.peek()
        if val == ";":
            self.next()
            return
        if val == "{":
            self.next()
            while self.peek()[1] != "}":
                if self.peek()[0] is None:
                    raise _Stop("unterminated block")
                self.statement()
            self.next()
            return
        if val == "if":
            self.if_statement()
            return
        if val == "var":
            self.next()
            kind, val = self.peek()
        if val in _KEYWORD_STOPS:
            raise _Stop(self._context())
        if kind == "name":
            nxt = self.peek(1)[1]
            if nxt in ("=", "+=", "-="):
                name = self.next()[1]
                op = self.next()[1]
                value = self.expression()
                if op == "+=":
                    value = _js_add(self.scope.get(name), value)
                elif op == "-=":
                    value = _num(self.scope.get(name)) - _num(value)
                self.scope[name] = value
                if self.peek()[1] == ";":
                    self.next()
                return
        raise _Stop(self._context())

    def if_statement(self):
        self.expect("if")
        self.expect("(")
        cond = self.expression()
        self.expect(")")
        if _truthy(cond):
            self.statement()
            if self.peek()[1] == "else":
                self.next()
                self.skip_statement()
        else:
            self.skip_statement()
            if self.peek()[1] == "else":
                self.next()
                self.statement()

    def skip_statement(self):
        """Skip the not-taken branch WITHOUT evaluating - but its syntax
        must still be inside the subset, or offsets drift."""
        kind, val = self.peek()
        if val == "{":
            depth = 0
            while True:
                kind, val = self.next()
                if kind is None:
                    raise _Stop("unterminated block")
                if val == "{":
                    depth += 1
                elif val == "}":
                    depth -= 1
                    if depth == 0:
                        return
        if val == "if":
            self.next()
            self.expect("(")
            depth = 1
            while depth:
                kind, v = self.next()
                if kind is None:
                    raise _Stop("unterminated condition")
                depth += (v == "(") - (v == ")")
            self.skip_statement()
            if self.peek()[1] == "else":
                self.next()
                self.skip_statement()
            return
        # simple statement: consume through the terminating ;
        while True:
            kind, v = self.next()
            if kind is None or v == ";":
                return

    # ---- expressions (precedence climbing) -------------------------------
    def expression(self):
        return self.or_expr()

    def or_expr(self):
        left = self.and_expr()
        while self.peek()[1] == "||":
            self.next()
            right = self.and_expr()
            left = _truthy(left) or _truthy(right)
        return left

    def and_expr(self):
        left = self.compare()
        while self.peek()[1] == "&&":
            self.next()
            right = self.compare()
            left = _truthy(left) and _truthy(right)
        return left

    def compare(self):
        left = self.additive()
        while self.peek()[1] in ("==", "!=", "<", ">", "<=", ">="):
            op = self.next()[1]
            right = self.additive()
            if op == "==":
                left = _js_eq(left, right)
            elif op == "!=":
                left = not _js_eq(left, right)
            else:
                lnum, rnum = _num(left), _num(right)
                left = {"<": lnum < rnum, ">": lnum > rnum,
                        "<=": lnum <= rnum, ">=": lnum >= rnum}[op]
        return left

    def additive(self):
        left = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.next()[1]
            right = self.term()
            left = _js_add(left, right) if op == "+" \
                else _num(left) - _num(right)
        return left

    def term(self):
        left = self.unary()
        while self.peek()[1] in ("*", "/", "%"):
            op = self.next()[1]
            right = self.unary()
            if op == "*":
                left = _num(left) * _num(right)
            elif op == "/":
                left = _num(left) / _num(right)
            else:
                left = _num(left) % _num(right)
        return left

    def unary(self):
        kind, val = self.peek()
        if val == "!":
            self.next()
            return not _truthy(self.unary())
        if val == "-":
            self.next()
            return -_num(self.unary())
        if val == "+":
            self.next()
            return _num(self.unary())
        return self.primary()

    def primary(self):
        kind, val = self.next()
        if val == "(":
            inner = self.expression()
            self.expect(")")
            return self.postfix(inner)
        if kind == "string":
            return self.postfix(_unquote(val))
        if kind == "number":
            return self.postfix(float(val) if "." in val else int(val))
        if kind == "name":
            if val == "null":
                return None
            if val == "true":
                return True
            if val == "false":
                return False
            if val in _KEYWORD_STOPS:
                raise _Stop(val)
            return self.postfix(self.scope.get(val))
        raise _Stop(str(val))

    def postfix(self, value):
        """`.toString()` is the one method the corpus leans on; anything
        else after a `.` is outside the subset."""
        while self.peek()[1] == ".":
            if (self.peek(1)[1] == "toString" and self.peek(2)[1] == "("
                    and self.peek(3)[1] == ")"):
                for _ in range(4):
                    self.next()
                value = _js_str(value)
            else:
                raise _Stop(self._context())
        return value


# ---- JavaScript value semantics -----------------------------------------

def _unquote(raw):
    body = raw[1:-1]
    return re.sub(r"\\(.)",
                  lambda m: {"n": "\n", "t": "\t", "r": "\r"}.get(
                      m.group(1), m.group(1)), body)


def _js_str(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _js_add(left, right):
    if isinstance(left, str) or isinstance(right, str):
        return _js_str(left) + _js_str(right)
    return _num(left) + _num(right)


def _num(value):
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            return 0
    return value


def _js_eq(left, right):
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) == float(right)
    return _js_str(left) == _js_str(right)


def _truthy(value):
    return bool(value) and value != ""


# ---- public entry --------------------------------------------------------

def evaluate_script(script, inputs, outputs, max_len=6000):
    """Run one JavascriptRule script over the sequence's input defaults.

    Returns ``(values, stopped_at)``: ``values`` maps each declared
    output assigned during the run to its STRING value (the platform
    substituted strings); ``stopped_at`` is None for a full run, else
    the source fragment where evaluation honestly gave up - everything
    in ``values`` was assigned before that point and is exact.
    """
    if not script or len(script) > max_len:
        return {}, (script or "")[:40] or "empty"
    scope = dict(inputs or {})
    stopped = None
    try:
        interp = _Interp(_tokenize(script), scope)
        interp.run()
    except _Stop as stop:
        stopped = stop.fragment
    except (RecursionError, ZeroDivisionError) as exc:
        stopped = type(exc).__name__
    values = {name: _js_str(scope[name]) for name in outputs
              if name in scope and not callable(scope[name])}
    return values, stopped

"""Expression translation (Stage 2: MAP, AI half).

Informatica expression language -> JavaScript for PDI's Modified Java Script
Value step. Two tiers, per the brief's hybrid principle:

1. Deterministic fast-path: expressions that are already valid JavaScript
   (plain arithmetic over ports) pass through untouched -> confidence AUTO.
2. LLM translation via the configured provider (Ollama), constrained by a
   function-mapping cheat sheet and forced JSON output. Every LLM translation
   is flagged REVIEW — Phase 0 mandates human review of AI output.

Failures never block a conversion: an untranslatable expression stays an
explicit TODO in the generated step.
"""

import json
import re

import httpx

from pdi_migration.ir import Confidence, Expression, Pipeline
from pdi_migration.llm.settings import LLMSettings, load_settings


class TranslationError(Exception):
    """Provider unavailable/misconfigured — translation cannot run at all."""


# Safe = identifiers, numbers, arithmetic, parens. No function calls, no
# Informatica operators (||, AND, OR), no strings -> valid JS as-is.
_SAFE_RE = re.compile(r"^[\w\s+\-*/().]*$")
_FUNC_RE = re.compile(r"[A-Za-z_]\w*\s*\(")
_KEYWORD_RE = re.compile(r"\b(AND|OR|NOT|TRUE|FALSE|NULL)\b", re.IGNORECASE)


def translate_deterministic(raw: str) -> str | None:
    """Return the expression unchanged if it is already JavaScript-safe."""
    if _SAFE_RE.match(raw) and not _FUNC_RE.search(raw) and not _KEYWORD_RE.search(raw):
        return raw.strip()
    return None


SYSTEM_PROMPT = """\
You translate Informatica PowerCenter expression-language snippets into JavaScript
for Pentaho Data Integration's "Modified Java Script Value" step.

Rules:
- Port/field names stay exactly as written.
- Informatica string positions are 1-based; JavaScript is 0-based — adjust.
- Reply with JSON only: {"translation": "<javascript>", "confidence": "high"|"medium"|"low", "notes": "<caveats or empty>"}
- If you are not certain the semantics match exactly, use confidence "medium" or "low" and say why in notes.
- Mapping-parameter references like $$PARAM cannot be resolved here: keep them as-is and use confidence "low".

Function mappings (authoritative — prefer these):
IIF(c, a, b)                -> (c) ? a : b
ISNULL(x)                   -> (x == null)
DECODE(x, v1, r1, v2, r2, d)-> (x == v1) ? r1 : (x == v2) ? r2 : d
a || b                      -> a + b            (string concat)
CONCAT(a, b)                -> a + b
SUBSTR(s, start, len)       -> s.substr(start - 1, len)
INSTR(s, sub)               -> (s.indexOf(sub) + 1)
LENGTH(s)                   -> s.length
UPPER(s) / LOWER(s)         -> s.toUpperCase() / s.toLowerCase()
LTRIM(s) / RTRIM(s)         -> ltrim(s) / rtrim(s)          (Kettle JS helpers)
TO_DATE(s, 'MM/DD/YYYY')    -> str2date(s, "MM/dd/yyyy")    (convert the format string to Java pattern)
TO_CHAR(d, 'YYYYMMDD')      -> date2str(d, "yyyyMMdd")
TO_CHAR(n)                  -> "" + n
TO_DECIMAL(s) / TO_FLOAT(s) / TO_INTEGER(s) -> str2num(s)
SYSDATE                     -> new Date()
MOD(a, b)                   -> a % b
ABS(x)                      -> Math.abs(x)
ROUND(x)                    -> Math.round(x)
AND / OR / NOT              -> && / || / !

Example:
Input:  IIF(ISNULL(AMOUNT), 0, AMOUNT * 1.2)
Output: {"translation": "(AMOUNT == null) ? 0 : AMOUNT * 1.2", "confidence": "high", "notes": ""}
"""

JAVA_PROMPT = """\
You translate Java expressions from Talend components (tMap, tFilterRow, tJavaRow)
into JavaScript for Pentaho Data Integration's "Modified Java Script Value" step.

Rules:
- Row aliases like row1.CUSTOMER_ID or out1.TOTAL refer to stream fields — drop the
  alias and use the bare field name (CUSTOMER_ID). Do NOT drop class prefixes like Math.
- Reply with JSON only: {"translation": "<javascript>", "confidence": "high"|"medium"|"low", "notes": "<caveats or empty>"}
- If semantics may differ, use confidence "medium"/"low" and explain in notes.

Mappings (authoritative — prefer these):
a.equals(b)                          -> a == b        (string compare)
!a.equals(b)                         -> a != b
StringHandling.UPCASE(s) / DOWNCASE  -> s.toUpperCase() / s.toLowerCase()
StringHandling.TRIM(s)               -> trim(s)
StringHandling.LEN(s)                -> s.length
s.substring(a, b)                    -> s.substring(a, b)
TalendDate.getCurrentDate()          -> new Date()
TalendDate.parseDate("yyyy-MM-dd", s)-> str2date(s, "yyyy-MM-dd")
TalendDate.formatDate("yyyy-MM-dd",d)-> date2str(d, "yyyy-MM-dd")
Integer.parseInt(s) / Double.parseDouble(s) -> str2num(s)
String.valueOf(x)                    -> "" + x
condition ? a : b                    -> unchanged
x == null / x != null                -> unchanged
Numeric.sequence("s1", 1, 1)         -> use a PDI Add sequence step instead — confidence "low"
context.NAME                         -> getVariable("NAME", "") — confidence "low" (map to a PDI parameter)
globalMap.get("key")                 -> no direct equivalent — confidence "low"
"""

CRYSTAL_PROMPT = """\
You translate SAP Crystal Reports formulas into Pentaho OpenFormula for
Pentaho Report Designer. The deterministic translator has already handled the
simple formulas; you only see the hard ones (variables, evaluation-time
directives, Select Case, arrays).

Syntax rules (authoritative):
- Field references: {Table.FIELD} -> [FIELD]; {@FormulaName} -> [FormulaName]; {?Param} -> [Param]
- Function arguments are separated by ';' not ',' — e.g. IF(c;a;b)
- If c Then a Else b            -> IF(c;a;b)   (nest for ElseIf chains)
- Select Case                   -> nested IF(...)
- and / or / not are NOT infix operators -> AND(x;y), OR(x;y), NOT(x)
- String concat & or +          -> &
- a Mod b                       -> MOD(a;b)
- Comparisons = <> < > <= >=    -> unchanged
- ToText(x) -> TEXT(x); ToNumber(x) -> VALUE(x); UpperCase/LowerCase -> UPPER/LOWER
- Trim -> TRIM; Left/Right/Mid -> LEFT/RIGHT/MID; Length -> LEN
- InStr(s, sub) -> FIND(sub; s)  (arguments swap)
- IsNull({f}) -> ISBLANK([f]); CurrentDate -> TODAY(); CurrentDateTime -> NOW()
- Reply with JSON only: {"translation": "<openformula WITHOUT leading =>", "confidence": "high"|"medium"|"low", "notes": "<caveats or empty>"}

Constructs with NO OpenFormula equivalent — do not fake them:
- Variables (Shared/Global/Local ...Var) that accumulate across records
  (running totals, counters): set translation to "" and confidence "low", and
  say in notes which PRD report function to use instead (ItemSumFunction,
  ItemCountFunction, or a custom function) and where to place it.
- WhilePrintingRecords / WhileReadingRecords / EvaluateAfter are evaluation-time
  directives: if the remaining body is a pure expression, translate the body and
  note that PRD's evaluation model differs; otherwise treat as above.
- Aggregates like Sum({f}, {group}): translation "" + note to use the
  matching Item*Function with the field and group.
- A variable used only as a local alias within one formula CAN be inlined:
  substitute the expression and translate normally (confidence "medium").

Example:
Input:  Local StringVar s := {Cust.FIRST} + " " + {Cust.LAST}; UpperCase(s)
Output: {"translation": "UPPER([FIRST] & \\" \\" & [LAST])", "confidence": "medium", "notes": "local alias inlined"}
"""

PROMPTS = {"informatica": SYSTEM_PROMPT, "java": JAVA_PROMPT, "crystal": CRYSTAL_PROMPT}

LANG_LABELS = {
    "informatica": "Informatica expression (output port '{field}')",
    "java": "Talend Java expression (target field '{field}')",
    "crystal": "Crystal Reports formula ({{@{field}}})",
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "translation": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": {"type": "string"},
    },
    "required": ["translation", "confidence"],
}


class ExpressionTranslator:
    def __init__(self, settings: LLMSettings | None = None, timeout: float = 120.0):
        self.settings = settings or load_settings()
        self.timeout = timeout

    def translate_pipeline(self, pipeline: Pipeline, progress=None) -> int:
        """Translate every untranslated expression in place; returns the count
        successfully translated. Raises TranslationError only if the provider
        is unusable; per-expression failures become notes, not crashes.
        `progress(done, total)` is called after each expression."""
        from pdi_migration.generator.ktr import AGGREGATE_RE

        self._check_provider()
        pending = [
            (step, expr)
            for step in pipeline.steps
            for expr in step.expressions
            if expr.translated is None
        ]
        translated = done = 0
        for step, expr in pending:
            # Group By aggregates are emitted as native aggregation config
            # by the generator — nothing to translate.
            if step.pdi_type == "GroupBy" and AGGREGATE_RE.match(expr.raw):
                expr.translated = expr.raw
                expr.confidence = Confidence.AUTO
                expr.notes = "handled natively as a Group By aggregation"
                translated += 1
            elif self.translate(expr).translated is not None:
                translated += 1
            done += 1
            if progress:
                progress(done, len(pending))
        return translated

    def translate(self, expr: Expression) -> Expression:
        # The deterministic fast-path is Informatica-only: Java expressions carry
        # row aliases (row1.FIELD) that must be rewritten, so they always go to
        # the LLM with the alias rule in the prompt.
        if expr.language == "informatica" and (
            (simple := translate_deterministic(expr.raw)) is not None
        ):
            expr.translated = simple
            expr.confidence = Confidence.AUTO
            expr.notes = "passthrough: already valid JavaScript"
            return expr
        try:
            result = self._chat(expr)
        except Exception as exc:
            expr.notes = f"translation failed: {exc}"
            return expr
        expr.translated = result["translation"]
        expr.confidence = Confidence.REVIEW  # every LLM output gets human review
        notes = [f"LLM confidence: {result.get('confidence', 'unknown')}"]
        if result.get("notes"):
            notes.append(result["notes"])
        expr.notes = "; ".join(notes)
        return expr

    def _check_provider(self) -> None:
        if self.settings.provider == "none":
            raise TranslationError(
                "LLM translation is disabled — choose a provider in Settings."
            )
        if self.settings.provider == "anthropic":
            raise TranslationError(
                "The Anthropic provider is not implemented yet — use Ollama."
            )
        if not self.settings.model:
            raise TranslationError(
                "No Ollama model configured — open Settings and apply the recommendation."
            )

    def _chat(self, expr: Expression) -> dict:
        """One expression -> one structured Ollama chat call."""
        response = httpx.post(
            f"{self.settings.base_url}/api/chat",
            json={
                "model": self.settings.model,
                "messages": [
                    {"role": "system", "content": PROMPTS.get(expr.language, SYSTEM_PROMPT)},
                    {
                        "role": "user",
                        "content": "Translate this "
                                   + LANG_LABELS.get(expr.language, LANG_LABELS["informatica"]).format(field=expr.field)
                                   + f":\n{expr.raw}",
                    },
                ],
                "stream": False,
                "format": RESPONSE_SCHEMA,
                "options": {"temperature": 0},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])

"""LLM assist for Crystal formulas the deterministic translator flagged manual.

Same hybrid contract as ETL expression translation: the LLM only sees what
deterministic rules could not prove, every LLM output is flagged `review` for
mandatory human verification, and failures never block — a formula that stays
untranslatable keeps its `manual` status, but gains the LLM's rebuild advice
(e.g. "use ItemSumFunction") in its notes.
"""

from pdi_migration.ir import Expression
from pdi_migration.llm import ExpressionTranslator
from pdi_migration.reports.model import ReportModel


def translate_manual_formulas(
    model: ReportModel,
    translator: ExpressionTranslator | None = None,
    progress=None,
) -> int:
    """Run every `manual` formula through the LLM. Returns how many became
    `review`. Raises TranslationError only if the provider is unusable;
    per-formula failures stay `manual` with the reason noted.
    `progress(done, total)` is called after each formula."""
    translator = translator or ExpressionTranslator()
    translator._check_provider()

    pending = [f for f in model.formulas.values() if f.status == "manual"]
    translated = 0
    for done, formula in enumerate(pending, start=1):
        expr = Expression(field=formula.name, raw=formula.text, language="crystal")
        translator.translate(expr)
        llm_notes = [n for n in (expr.notes or "").split("; ") if n]
        if expr.translated:
            formula.translation = "=" + expr.translated.lstrip("=")
            formula.status = "review"
            formula.notes = ["AI-translated — verify semantics in PRD", *llm_notes]
            translated += 1
        elif llm_notes:
            # untranslatable, but the LLM's rebuild advice is still valuable
            formula.notes = [*formula.notes, *llm_notes]
        if progress:
            progress(done, len(pending))
    return translated

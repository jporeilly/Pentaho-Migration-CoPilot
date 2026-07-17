"""LLM expression translator (Stage 2: MAP, AI half). NOT YET IMPLEMENTED.

Will translate Informatica expression-language snippets (IIF, DECODE,
TO_DATE, ...) into PDI equivalents, constrained by the rules library and
validated examples. Low-confidence translations are flagged for review,
never silently accepted.
"""

from pdi_migration.ir import Expression


class LLMTranslator:
    def translate(self, expression: Expression) -> Expression:
        raise NotImplementedError(
            "LLM expression translation is planned for a later milestone; "
            "expressions currently pass through with confidence=manual."
        )

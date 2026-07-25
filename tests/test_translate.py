"""Expression translation: deterministic fast-path, mocked-LLM pipeline flow,
KTR emission of translations, and API error handling."""

from pathlib import Path
from xml.etree import ElementTree

from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.generator import KtrGenerator
from pentaho_migration.ir import Confidence
from pentaho_migration.llm import ExpressionTranslator, LLMSettings
from pentaho_migration.llm.translate import translate_deterministic
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import PowerCenterParser
from pentaho_migration.validator import build_report

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"

OLLAMA_SETTINGS = LLMSettings(provider="ollama", model="test-model")


class FakeTranslator(ExpressionTranslator):
    """LLM calls replaced with a canned response."""

    def _chat(self, expr):
        return {
            "translation": f"/* fake */ {expr.field}",
            "confidence": "high",
            "notes": "canned",
        }


def _mapped_pipeline():
    (pipeline,) = PowerCenterParser().parse_file(SAMPLE)
    return RulesMapper().apply(pipeline)


class TestDeterministic:
    def test_plain_arithmetic_passes_through(self):
        assert translate_deterministic("AMOUNT * 1.2") == "AMOUNT * 1.2"

    def test_function_calls_go_to_llm(self):
        assert translate_deterministic("IIF(ISNULL(A), 0, A)") is None

    def test_informatica_operators_go_to_llm(self):
        assert translate_deterministic("FIRST || LAST") is None
        assert translate_deterministic("A AND B") is None


class TestPipelineTranslation:
    def test_translates_all_expressions(self):
        pipeline = _mapped_pipeline()
        count = FakeTranslator(OLLAMA_SETTINGS).translate_pipeline(pipeline)
        assert count == 2
        assert build_report(pipeline).untranslated_expressions == 0

    def test_llm_translations_are_flagged_review(self):
        pipeline = _mapped_pipeline()
        FakeTranslator(OLLAMA_SETTINGS).translate_pipeline(pipeline)
        expr = pipeline.step("EXP_CALC").expressions[0]
        assert expr.translated.startswith("/* fake */")
        assert expr.confidence == Confidence.REVIEW
        assert "LLM confidence: high" in expr.notes

    def test_chat_failure_leaves_expression_untranslated(self):
        class BrokenTranslator(ExpressionTranslator):
            def _chat(self, expr):
                raise RuntimeError("connection refused")

        pipeline = _mapped_pipeline()
        count = BrokenTranslator(OLLAMA_SETTINGS).translate_pipeline(pipeline)
        # the Group By aggregate still converts deterministically without the LLM
        assert count == 1
        expr = pipeline.step("EXP_CALC").expressions[0]
        assert expr.translated is None
        assert "translation failed" in expr.notes
        agg = pipeline.step("AGG_SALES").expressions[0]
        assert agg.translated is not None
        assert agg.confidence == Confidence.AUTO

    def test_translated_js_lands_in_ktr_script(self):
        pipeline = _mapped_pipeline()
        FakeTranslator(OLLAMA_SETTINGS).translate_pipeline(pipeline)
        root = ElementTree.fromstring(KtrGenerator().generate(pipeline))
        exp = next(s for s in root.iter("step") if s.findtext("name") == "EXP_CALC")
        script = exp.findtext("jsScripts/jsScript/jsScript_script")
        assert "var AMOUNT_TAXED = /* fake */ AMOUNT_TAXED;" in script
        assert "TODO translate" not in script
        assert "TODO expression" not in exp.findtext("description")


class TestTranslateAPI:
    def test_disabled_provider_returns_503(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
        client = TestClient(app)
        client.put("/settings", json={"provider": "none", "base_url": "", "model": None, "env": {}})
        pipeline = _mapped_pipeline()
        res = client.post("/translate", json=pipeline.model_dump())
        assert res.status_code == 503
        assert "disabled" in res.json()["detail"]

    def test_missing_model_returns_503(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
        client = TestClient(app)
        pipeline = _mapped_pipeline()
        res = client.post("/translate", json=pipeline.model_dump())
        assert res.status_code == 503
        assert "No Ollama model" in res.json()["detail"]

    def test_job_flow_start_poll_done(self, tmp_path, monkeypatch):
        import time

        monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(
            "pentaho_migration.llm.translate.ExpressionTranslator._chat",
            FakeTranslator._chat,
        )
        client = TestClient(app)
        client.put("/settings", json={
            "provider": "ollama", "base_url": "http://127.0.0.1:11434",
            "model": "test-model", "env": {},
        })
        pipeline = _mapped_pipeline()
        res = client.post("/translate/start", json=pipeline.model_dump())
        assert res.status_code == 200
        job = res.json()["job"]

        for _ in range(50):
            state = client.get(f"/translate/status?job={job}").json()
            if state["status"] != "running":
                break
            time.sleep(0.1)
        assert state["status"] == "done"
        assert state["result"]["report"]["untranslated_expressions"] == 0
        assert "/* fake */" in state["result"]["ktr"]

    def test_job_status_unknown_404(self):
        client = TestClient(app)
        assert client.get("/translate/status?job=nope").status_code == 404

    def test_translate_returns_updated_result(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(
            "pentaho_migration.llm.translate.ExpressionTranslator._chat",
            FakeTranslator._chat,
        )
        client = TestClient(app)
        client.put("/settings", json={
            "provider": "ollama", "base_url": "http://127.0.0.1:11434",
            "model": "test-model", "env": {},
        })
        pipeline = _mapped_pipeline()
        res = client.post("/translate", json=pipeline.model_dump())
        assert res.status_code == 200
        body = res.json()
        assert body["report"]["untranslated_expressions"] == 0
        assert "/* fake */" in body["ktr"]

# ------------------------------------------------------------ Anthropic provider

def test_anthropic_provider_gating_without_key(monkeypatch):
    """Anthropic provider needs the SDK and an API key - clear errors, not a stub."""
    import sys

    import pytest

    from pentaho_migration.llm import TranslationError

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake_anthropic = type(sys)("anthropic")
    fake_anthropic.APIError = Exception
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    t = ExpressionTranslator(LLMSettings(provider="anthropic", api_key=""))
    with pytest.raises(TranslationError):
        t._check_provider()

    # with a key, gating passes
    ExpressionTranslator(LLMSettings(provider="anthropic", api_key="sk-x"))._check_provider()


def test_anthropic_chat_parses_json_and_flags_review(monkeypatch):
    """The Claude Messages call returns JSON text; it becomes a review-flagged
    translation using the configured model."""
    import sys
    from unittest.mock import MagicMock

    from pentaho_migration.ir import Confidence, Expression

    block = MagicMock(type="text",
                      text='```json\n{"translation": "(A==null)?0:A", '
                           '"confidence": "high", "notes": "ok"}\n```')
    message = MagicMock(content=[block])
    client = MagicMock()
    client.messages.create.return_value = message
    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic.return_value = client
    fake_anthropic.APIError = Exception
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    t = ExpressionTranslator(LLMSettings(provider="anthropic", api_key="sk-x",
                                         model="claude-opus-5"))
    expr = Expression(field="X", raw="IIF(ISNULL(A),0,A)", language="informatica")
    t.translate(expr)

    assert expr.translated == "(A==null)?0:A"          # fenced JSON stripped
    assert expr.confidence == Confidence.REVIEW         # every LLM output is review
    assert client.messages.create.call_args.kwargs["model"] == "claude-opus-5"


# ------------------------------------------------- OpenAI / Google / Azure

def test_openai_family_gating_without_key(monkeypatch):
    """OpenAI, Google and Azure all need the openai SDK and an API key."""
    import sys

    import pytest

    from pentaho_migration.llm import TranslationError

    fake_openai = type(sys)("openai")
    fake_openai.OpenAIError = Exception
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    for provider, env in [("openai", "OPENAI_API_KEY"),
                          ("google", "GEMINI_API_KEY"),
                          ("azure", "AZURE_OPENAI_API_KEY")]:
        monkeypatch.delenv(env, raising=False)
        with pytest.raises(TranslationError):
            ExpressionTranslator(LLMSettings(provider=provider, api_key=""))._check_provider()
    # Azure additionally needs the resource endpoint in base_url
    with pytest.raises(TranslationError):
        ExpressionTranslator(
            LLMSettings(provider="azure", api_key="k", base_url=""))._check_provider()
    # ...supplied, gating passes
    ExpressionTranslator(LLMSettings(
        provider="azure", api_key="k",
        base_url="https://r.openai.azure.com"))._check_provider()


def test_openai_chat_parses_json_and_flags_review(monkeypatch):
    """The OpenAI-compatible completion returns a JSON object; it becomes a
    review-flagged translation using the configured model. Google Gemini and
    Azure OpenAI share this exact code path."""
    import sys
    from unittest.mock import MagicMock

    from pentaho_migration.ir import Confidence, Expression

    message = MagicMock(content='{"translation": "A + B", "confidence": "high", "notes": ""}')
    completion = MagicMock(choices=[MagicMock(message=message)])
    client = MagicMock()
    client.chat.completions.create.return_value = completion
    fake_openai = MagicMock()
    fake_openai.OpenAI.return_value = client
    fake_openai.OpenAIError = Exception
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    t = ExpressionTranslator(LLMSettings(provider="openai", api_key="sk-x", model="gpt-4o"))
    expr = Expression(field="X", raw="A || B", language="informatica")
    t.translate(expr)

    assert expr.translated == "A + B"
    assert expr.confidence == Confidence.REVIEW
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["response_format"] == {"type": "json_object"}

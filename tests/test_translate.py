"""Expression translation: deterministic fast-path, mocked-LLM pipeline flow,
KTR emission of translations, and API error handling."""

from pathlib import Path
from xml.etree import ElementTree

from fastapi.testclient import TestClient

from pdi_migration.api.main import app
from pdi_migration.generator import KtrGenerator
from pdi_migration.ir import Confidence
from pdi_migration.llm import ExpressionTranslator, LLMSettings
from pdi_migration.llm.translate import translate_deterministic
from pdi_migration.mapper import RulesMapper
from pdi_migration.parser import PowerCenterParser
from pdi_migration.validator import build_report

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
        monkeypatch.setenv("PDI_MIGRATION_CONFIG_DIR", str(tmp_path))
        client = TestClient(app)
        client.put("/settings", json={"provider": "none", "base_url": "", "model": None, "env": {}})
        pipeline = _mapped_pipeline()
        res = client.post("/translate", json=pipeline.model_dump())
        assert res.status_code == 503
        assert "disabled" in res.json()["detail"]

    def test_missing_model_returns_503(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PDI_MIGRATION_CONFIG_DIR", str(tmp_path))
        client = TestClient(app)
        pipeline = _mapped_pipeline()
        res = client.post("/translate", json=pipeline.model_dump())
        assert res.status_code == 503
        assert "No Ollama model" in res.json()["detail"]

    def test_translate_returns_updated_result(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PDI_MIGRATION_CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(
            "pdi_migration.llm.translate.ExpressionTranslator._chat",
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
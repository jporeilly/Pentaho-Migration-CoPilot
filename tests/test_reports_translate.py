"""LLM assist for Crystal formulas: mocked-LLM unit flow, the untranslatable
path (advice lands in notes, status stays manual), provider gating, and the
/reports/translate background-job API."""

import base64
import time
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.llm import ExpressionTranslator, LLMSettings, TranslationError
from pentaho_migration.reports import load_report_model
from pentaho_migration.reports.llm_assist import translate_manual_formulas

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "branch_transactions.xml"

OLLAMA_SETTINGS = LLMSettings(provider="ollama", model="test-model")

client = TestClient(app)


class FakeTranslator(ExpressionTranslator):
    """LLM calls replaced with a canned OpenFormula response."""

    def _chat(self, expr):
        return {
            "translation": "[AMOUNT] * 1",
            "confidence": "medium",
            "notes": "canned",
        }


class AdviceOnlyTranslator(ExpressionTranslator):
    """The no-equivalent path: empty translation, rebuild advice in notes."""

    def _chat(self, expr):
        return {
            "translation": "",
            "confidence": "low",
            "notes": "running total — use ItemSumFunction on AMOUNT instead",
        }


def test_manual_formula_becomes_review():
    model = load_report_model(SAMPLE)
    count = translate_manual_formulas(model, FakeTranslator(OLLAMA_SETTINGS))
    assert count == 2
    f = model.formulas["RunningBalance"]
    assert f.status == "review"
    assert f.translation == "=[AMOUNT] * 1"
    assert any("AI-translated" in n for n in f.notes)
    assert any("LLM confidence: medium" in n for n in f.notes)
    # the auto formulas were never sent to the LLM
    assert model.formulas["FullName"].status == "auto"


def test_untranslatable_keeps_manual_but_gains_advice():
    model = load_report_model(SAMPLE)
    count = translate_manual_formulas(model, AdviceOnlyTranslator(OLLAMA_SETTINGS))
    assert count == 0
    f = model.formulas["RunningBalance"]
    assert f.status == "manual"
    assert f.translation == ""
    assert any("ItemSumFunction" in n for n in f.notes)
    # the original deterministic blocker note is preserved
    assert any("Blocked" in n for n in f.notes)


def test_provider_disabled_raises():
    model = load_report_model(SAMPLE)
    with pytest.raises(TranslationError):
        translate_manual_formulas(
            model, ExpressionTranslator(LLMSettings(provider="none")))


def test_api_translate_job(monkeypatch):
    monkeypatch.setattr(ExpressionTranslator, "_check_provider", lambda self: None)
    monkeypatch.setattr(
        ExpressionTranslator, "_chat",
        lambda self, expr: {"translation": "[AMOUNT] * 1", "confidence": "high", "notes": ""})

    res = client.post(
        "/reports/translate/start?jndi=CSCU_Bank",
        files={"dump": ("branch.xml", SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 200
    job = res.json()["job"]

    for _ in range(50):
        state = client.get(f"/reports/translate/status?job={job}").json()
        if state["status"] != "running":
            break
        time.sleep(0.1)
    assert state["status"] == "done"
    assert state["translated"] == 2

    result = state["result"]
    counts = result["summary"]["counts"]
    assert counts["manual"] == 0
    assert counts["review"] == 2

    # the assisted formula is baked into the regenerated .prpt
    prpt = base64.b64decode(result["prpt_base64"])
    dd = zipfile.ZipFile(BytesIO(prpt)).read("datadefinition.xml").decode()
    assert 'name="RunningBalance"' in dd


def test_api_translate_requires_provider(monkeypatch):
    # force "no provider configured" regardless of this machine's settings file
    import pentaho_migration.llm.translate as translate_mod

    monkeypatch.setattr(
        translate_mod, "load_settings", lambda: LLMSettings(provider="none"))
    res = client.post(
        "/reports/translate/start",
        files={"dump": ("branch.xml", SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 503


def test_api_unknown_job():
    assert client.get("/reports/translate/status?job=nope").status_code == 404

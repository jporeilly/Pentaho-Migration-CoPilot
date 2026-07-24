"""AI solution suggestions: context building and endpoint behavior."""

from pathlib import Path

from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.llm import LLMSettings
from pentaho_migration.llm.suggest import SolutionSuggester
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import TalendParser

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "demo_orders_0.1.item"


def _pipeline():
    (pipeline,) = TalendParser().parse_file(FIXTURE)
    return RulesMapper.for_pipeline(pipeline).apply(pipeline)


class TestContext:
    def test_context_includes_real_step_facts(self):
        suggester = SolutionSuggester(LLMSettings(provider="ollama", model="m"))
        context = suggester._context(_pipeline(), _pipeline().step("tMap_1"), {
            "differences": ["tMap is three PDI concepts in one"],
            "actions": ["Rebuild lookups"],
        })
        assert "Source tool: talend" in context
        assert "tMap_1" in context
        assert "StringHandling.UPCASE" in context     # real expression included
        assert "three PDI concepts" in context        # impact knowledge included
        assert "Upstream steps:" in context


class TestSuggestEndpoint:
    def test_returns_markdown_suggestion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(
            "pentaho_migration.llm.suggest.SolutionSuggester._chat",
            lambda self, context: "## Recommended approach\nUse Stream Lookup.",
        )
        client = TestClient(app)
        client.put("/settings", json={
            "provider": "ollama", "base_url": "http://127.0.0.1:11434",
            "model": "test-model", "env": {},
        })
        pipeline = _pipeline()
        res = client.post("/suggest", json={
            "pipeline": pipeline.model_dump(), "step": "tMap_1",
            "impact_entry": {"differences": [], "actions": []},
        })
        assert res.status_code == 200
        assert "Stream Lookup" in res.json()["suggestion"]

    def test_unknown_step_404(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
        client = TestClient(app)
        client.put("/settings", json={
            "provider": "ollama", "base_url": "http://127.0.0.1:11434",
            "model": "test-model", "env": {},
        })
        res = client.post("/suggest", json={
            "pipeline": _pipeline().model_dump(), "step": "nope",
        })
        assert res.status_code == 404

    def test_disabled_provider_503(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
        client = TestClient(app)
        client.put("/settings", json={"provider": "none", "base_url": "", "model": None, "env": {}})
        res = client.post("/suggest", json={
            "pipeline": _pipeline().model_dump(), "step": "tMap_1",
        })
        assert res.status_code == 503
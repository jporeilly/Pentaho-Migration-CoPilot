"""Model recommendation ladder + settings persistence/API."""

from fastapi.testclient import TestClient

from pdi_migration.api.main import app
from pdi_migration.llm.detect import ollama_base_url, recommend

client = TestClient(app)


class TestOllamaBaseUrl:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        assert ollama_base_url() == "http://127.0.0.1:11434"

    def test_listen_all_interfaces_maps_to_loopback(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0")
        assert ollama_base_url() == "http://127.0.0.1:11434"

    def test_explicit_host_port_preserved(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "gpu-box:11435")
        assert ollama_base_url() == "http://gpu-box:11435"


class TestRecommend:
    def test_big_gpu_gets_32b(self):
        assert recommend(ram_gb=64, vram_gb=24).model == "qwen2.5-coder:32b"

    def test_mid_gpu_gets_14b(self):
        assert recommend(ram_gb=32, vram_gb=12).model == "qwen2.5-coder:14b"

    def test_common_8gb_gpu_gets_7b(self):
        rec = recommend(ram_gb=32, vram_gb=8)
        assert rec.model == "qwen2.5-coder:7b"
        assert rec.env_suggestions["OLLAMA_FLASH_ATTENTION"] == "1"

    def test_cpu_only_uses_ram_ladder(self):
        assert recommend(ram_gb=32, vram_gb=None).model == "qwen2.5-coder:7b"
        assert recommend(ram_gb=16, vram_gb=None).model == "qwen2.5-coder:3b"
        assert recommend(ram_gb=8, vram_gb=None).model == "qwen2.5-coder:1.5b"

    def test_unknown_hardware_gets_safe_floor(self):
        assert recommend(ram_gb=None, vram_gb=None).model == "qwen2.5-coder:1.5b"


class TestSettingsAPI:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PDI_MIGRATION_CONFIG_DIR", str(tmp_path))
        payload = {
            "provider": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "qwen2.5-coder:7b",
            "env": {"OLLAMA_KEEP_ALIVE": "30m"},
        }
        res = client.put("/settings", json=payload)
        assert res.status_code == 200
        assert (tmp_path / "settings.json").exists()

        res = client.get("/settings")
        assert res.status_code == 200
        body = res.json()
        assert body["settings"]["model"] == "qwen2.5-coder:7b"
        assert body["detection"]["recommendation"]["model"].startswith("qwen2.5-coder")
        assert "ollama" in body["detection"]
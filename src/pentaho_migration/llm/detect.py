"""Ollama environment detection + model recommendation.

Inspects the host (RAM, NVIDIA VRAM, OLLAMA_* environment variables, a running
Ollama server) and recommends the best local model for the expression-translation
workload — small, code-oriented, structured output. Pure logic (recommend) is
separated from probing (detection_report) so it can be unit-tested.
"""

import ctypes
import os
import platform
import subprocess

import httpx
from pydantic import BaseModel

from pentaho_migration.llm.translate import CLOUD_PROVIDERS

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
PROBE_TIMEOUT = 2.0

# Env vars worth surfacing in the settings UI. Cloud API keys are reported
# presence-only — their values must never leave the machine.
OLLAMA_ENV_VARS = (
    "OLLAMA_HOST",
    "OLLAMA_MODELS",
    "OLLAMA_KEEP_ALIVE",
    "OLLAMA_NUM_PARALLEL",
    "OLLAMA_MAX_LOADED_MODELS",
    "OLLAMA_FLASH_ATTENTION",
    "OLLAMA_KV_CACHE_TYPE",
    "OLLAMA_SCHED_SPREAD",
)


class Recommendation(BaseModel):
    model: str
    reason: str
    env_suggestions: dict[str, str] = {}


class OllamaStatus(BaseModel):
    running: bool
    base_url: str
    version: str | None = None
    installed_models: list[str] = []


class DetectionReport(BaseModel):
    platform: str
    ram_gb: float | None
    vram_gb: float | None      # total across all GPUs
    gpu_name: str | None       # e.g. "2× NVIDIA GeForce RTX 3060"
    gpu_count: int = 0
    env: dict[str, str]
    anthropic_key_present: bool
    # presence-only per provider: {"anthropic": bool, "openai": ..., "google", "azure"}
    cloud_keys: dict[str, bool] = {}
    ollama: OllamaStatus
    recommendation: Recommendation


def ollama_base_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "").strip()
    if not host:
        return DEFAULT_OLLAMA_URL
    if "://" not in host:
        host = f"http://{host}"
    # OLLAMA_HOST is a *listen* address; 0.0.0.0 means "all interfaces" and is
    # not connectable — clients reach it via loopback. Default port if omitted.
    host = host.replace("//0.0.0.0", "//127.0.0.1").rstrip("/")
    if host.count(":") < 2:
        host = f"{host}:11434"
    return host


def total_ram_gb() -> float | None:
    try:
        if platform.system() == "Windows":
            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatusEx()
            status.dwLength = ctypes.sizeof(MemoryStatusEx)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return round(status.ullTotalPhys / 1024**3, 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except Exception:
        return None


def parse_nvidia_smi(output: str) -> tuple[str | None, float | None, int]:
    """(display_name, total_vram_gb, gpu_count) from nvidia-smi CSV output.
    Multiple GPUs aggregate VRAM — Ollama layer-splits models across them."""
    lines = [line for line in output.strip().splitlines() if line.strip()]
    if not lines:
        return None, None, 0
    names, total_mb = [], 0.0
    for line in lines:
        name, mem_mb = line.rsplit(",", 1)
        names.append(name.strip())
        total_mb += float(mem_mb)
    count = len(names)
    if count == 1:
        display = names[0]
    elif len(set(names)) == 1:
        display = f"{count}× {names[0]}"
    else:
        display = " + ".join(names)
    return display, round(total_mb / 1024, 1), count


def nvidia_gpu() -> tuple[str | None, float | None, int]:
    """(display_name, total_vram_gb, gpu_count) via nvidia-smi; (None, None, 0)
    without an NVIDIA GPU."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None, None, 0
        return parse_nvidia_smi(out.stdout)
    except Exception:
        return None, None, 0


def ollama_status() -> OllamaStatus:
    base = ollama_base_url()
    status = OllamaStatus(running=False, base_url=base)
    try:
        with httpx.Client(base_url=base, timeout=PROBE_TIMEOUT) as client:
            status.version = client.get("/api/version").json().get("version")
            status.running = True
            tags = client.get("/api/tags").json()
            status.installed_models = sorted(m["name"] for m in tags.get("models", []))
    except Exception:
        pass
    return status


def recommend(
    ram_gb: float | None, vram_gb: float | None, gpu_count: int = 1
) -> Recommendation:
    """Pick a code-oriented model sized to the hardware.

    Expression translation is a short-context structured-code task, so the
    qwen2.5-coder family is the default ladder; the constraint is memory.
    Multi-GPU rigs aggregate VRAM (Ollama layer-splits across cards).
    """
    env = {
        "OLLAMA_KEEP_ALIVE": "30m",   # batch translation: keep the model warm between mappings
        "OLLAMA_NUM_PARALLEL": "2",   # short prompts; mild parallelism is safe
    }
    multi = gpu_count > 1
    if multi:
        env["OLLAMA_SCHED_SPREAD"] = "1"  # spread layers across all GPUs
    if vram_gb:
        env["OLLAMA_FLASH_ATTENTION"] = "1"
        if vram_gb >= 24:
            split_note = (
                f" split across {gpu_count} GPUs — best quality; qwen2.5-coder:14b "
                "on a single card is the faster alternative" if multi
                else " fully on GPU — best translation quality"
            )
            return Recommendation(
                model="qwen2.5-coder:32b",
                reason=f"{vram_gb} GB total VRAM fits the 32B coder model{split_note}.",
                env_suggestions=env,
            )
        if vram_gb >= 12:
            return Recommendation(
                model="qwen2.5-coder:14b",
                reason=f"{vram_gb} GB VRAM fits the 14B coder model on GPU with headroom for context.",
                env_suggestions=env,
            )
        if vram_gb >= 6:
            return Recommendation(
                model="qwen2.5-coder:7b",
                reason=f"{vram_gb} GB VRAM fits the 7B coder model — strong quality/speed balance for expression translation.",
                env_suggestions=env,
            )
        return Recommendation(
            model="qwen2.5-coder:3b",
            reason=f"{vram_gb} GB VRAM is tight; the 3B coder model stays fully on GPU.",
            env_suggestions=env,
        )
    if ram_gb and ram_gb >= 32:
        return Recommendation(
            model="qwen2.5-coder:7b",
            reason=f"No NVIDIA GPU detected; {ram_gb} GB RAM runs the 7B coder model on CPU (slower but accurate).",
            env_suggestions=env,
        )
    if ram_gb and ram_gb >= 16:
        return Recommendation(
            model="qwen2.5-coder:3b",
            reason=f"No NVIDIA GPU detected; {ram_gb} GB RAM suits the 3B coder model on CPU.",
            env_suggestions=env,
        )
    return Recommendation(
        model="qwen2.5-coder:1.5b",
        reason="Limited memory detected; the 1.5B coder model is the safe floor — expect reduced quality.",
        env_suggestions=env,
    )


def detection_report() -> DetectionReport:
    ram = total_ram_gb()
    gpu_name, vram, gpu_count = nvidia_gpu()
    return DetectionReport(
        platform=f"{platform.system()} {platform.release()}",
        ram_gb=ram,
        vram_gb=vram,
        gpu_name=gpu_name,
        gpu_count=gpu_count,
        env={k: v for k in OLLAMA_ENV_VARS if (v := os.environ.get(k))},
        anthropic_key_present=bool(os.environ.get("ANTHROPIC_API_KEY")),
        cloud_keys={
            provider: bool(os.environ.get(spec["env"]))
            for provider, spec in CLOUD_PROVIDERS.items()
        },
        ollama=ollama_status(),
        recommendation=recommend(ram, vram, gpu_count),
    )

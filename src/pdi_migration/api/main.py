"""FastAPI layer — a thin wrapper over the core package.

Run with:  uvicorn pdi_migration.api.main:app --reload
Requires the [api] extra:  pip install -e ".[api]"

Phase 0 exposes parse + convert for the services team; the Phase 1 review UI
(React) will consume this same API.
"""

import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile

from pdi_migration import __version__
from pdi_migration.ir import Pipeline
from pdi_migration.mapper import RulesMapper
from pdi_migration.parser import PowerCenterParser
from pdi_migration.validator import MigrationReport, build_report

app = FastAPI(title="Migration Copilot", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/parse", response_model=list[Pipeline])
async def parse(export: UploadFile) -> list[Pipeline]:
    """Parse a PowerCenter XML export into the normalized IR."""
    return _parse_upload(await export.read())


@app.post("/convert", response_model=list[MigrationReport])
async def convert(export: UploadFile) -> list[MigrationReport]:
    """Parse + map a PowerCenter export; return per-pipeline migration reports."""
    mapper = RulesMapper()
    return [build_report(mapper.apply(p)) for p in _parse_upload(await export.read())]


def _parse_upload(data: bytes) -> list[Pipeline]:
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        return PowerCenterParser().parse_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

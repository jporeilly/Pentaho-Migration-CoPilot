"""FastAPI layer — a thin wrapper over the core package.

Run with:  uvicorn pdi_migration.api.main:app --reload
Requires the [api] extra:  pip install -e ".[api]"

Serves the Phase 0 review UI at / and the API under /parse, /convert.
Interactive API docs at /docs.
"""

import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pdi_migration import __version__
from pdi_migration.generator import KtrGenerator
from pdi_migration.ir import Pipeline
from pdi_migration.mapper import RulesMapper
from pdi_migration.parser import PowerCenterParser
from pdi_migration.parser.powercenter import PowerCenterParseError
from pdi_migration.validator import MigrationReport, build_report

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Migration Copilot", version=__version__)


class ConversionResult(BaseModel):
    pipeline: Pipeline
    report: MigrationReport
    ktr: str


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/parse", response_model=list[Pipeline])
async def parse(export: UploadFile) -> list[Pipeline]:
    """Parse a PowerCenter XML export into the normalized IR."""
    return _parse_upload(await export.read())


@app.post("/convert", response_model=list[ConversionResult])
async def convert(export: UploadFile) -> list[ConversionResult]:
    """Full conversion: parse -> map -> generate. Returns IR, report, and .ktr XML."""
    mapper = RulesMapper()
    generator = KtrGenerator()
    results = []
    for pipeline in _parse_upload(await export.read()):
        mapper.apply(pipeline)
        results.append(
            ConversionResult(
                pipeline=pipeline,
                report=build_report(pipeline),
                ktr=generator.generate(pipeline),
            )
        )
    return results


def _parse_upload(data: bytes) -> list[Pipeline]:
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        return PowerCenterParser().parse_file(tmp_path)
    except (PowerCenterParseError, SyntaxError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

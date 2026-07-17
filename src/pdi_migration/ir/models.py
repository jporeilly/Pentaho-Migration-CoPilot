"""Normalized intermediate representation (IR) for legacy ETL pipelines.

Every source tool (Informatica, SSIS, Talend, DataStage) parses into this
representation; the mapper and generator only ever see the IR, never the
source format.
"""

from enum import Enum

from pydantic import BaseModel, Field


class SourceTool(str, Enum):
    POWERCENTER = "powercenter"
    SSIS = "ssis"
    TALEND = "talend"
    DATASTAGE = "datastage"


class Confidence(str, Enum):
    """Per-step conversion confidence, surfaced in the migration report."""

    AUTO = "auto"          # rules-library 1:1 mapping; no review expected
    REVIEW = "review"      # LLM-translated or partial mapping; human should verify
    MANUAL = "manual"      # no mapping known; human must convert by hand


class FieldDef(BaseModel):
    name: str
    datatype: str = "string"
    precision: int | None = None
    scale: int | None = None
    nullable: bool = True
    attrs: dict[str, str] = Field(default_factory=dict)  # source-tool extras, e.g. PORTTYPE/EXPRESSIONTYPE


class Expression(BaseModel):
    """A source-tool expression attached to a field (e.g. an Informatica
    Expression-transformation output port)."""

    field: str
    raw: str
    language: str = "informatica"
    translated: str | None = None
    confidence: Confidence = Confidence.MANUAL


class Step(BaseModel):
    name: str
    source_type: str                      # e.g. "Aggregator", "Source Qualifier"
    pdi_type: str | None = None           # e.g. "GroupBy"; set by the mapper
    fields: list[FieldDef] = Field(default_factory=list)
    expressions: list[Expression] = Field(default_factory=list)
    properties: dict[str, str] = Field(default_factory=dict)
    confidence: Confidence = Confidence.MANUAL
    notes: list[str] = Field(default_factory=list)


class Hop(BaseModel):
    from_step: str
    to_step: str


class WarningLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    SERIOUS = "serious"


class SourceWarning(BaseModel):
    level: WarningLevel
    text: str


class SourceInfo(BaseModel):
    """Export-level facts about the source tool, surfaced before migration."""

    tool: str = "Informatica PowerCenter"
    repository_version: str | None = None   # e.g. "187.96"
    product_version: str | None = None      # e.g. "10.4.0"
    repository_name: str | None = None
    database_type: str | None = None
    codepage: str | None = None
    creation_date: str | None = None
    folders: list[str] = Field(default_factory=list)
    mappings: int = 0
    workflows: int = 0
    sessions: int = 0
    mapplets: int = 0
    warnings: list[SourceWarning] = Field(default_factory=list)


class Pipeline(BaseModel):
    name: str
    source_tool: SourceTool
    steps: list[Step] = Field(default_factory=list)
    hops: list[Hop] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    def step(self, name: str) -> Step | None:
        return next((s for s in self.steps if s.name == name), None)

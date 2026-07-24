"""Intermediate representation of a Crystal report, decoupled from both file formats.

All coordinates and sizes are in points (1/72 inch). RptToXml emits twips
(1/1440 inch); the parser divides by 20 on the way in.
"""

from dataclasses import dataclass, field
from typing import Optional


TWIPS_PER_POINT = 20.0

# Crystal summary operation -> PRD report function. Lives here (not in the
# writer) so the parser can flag unsupported operations at load time instead
# of the writer silently dropping them.
SUMMARY_CLASS_MAP = {
    "Sum": "org.pentaho.reporting.engine.classic.core.function.ItemSumFunction",
    "Count": "org.pentaho.reporting.engine.classic.core.function.ItemCountFunction",
    "Average": "org.pentaho.reporting.engine.classic.core.function.ItemAvgFunction",
    "Maximum": "org.pentaho.reporting.engine.classic.core.function.ItemMaxFunction",
    "Minimum": "org.pentaho.reporting.engine.classic.core.function.ItemMinFunction",
    "DistinctCount": "org.pentaho.reporting.engine.classic.core.function.CountDistinctFunction",
}


@dataclass
class Font:
    name: str = "Arial"
    size: float = 10.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: Optional[str] = None  # #rrggbb


@dataclass
class Element:
    """A single report object placed in a section."""

    kind: str  # label | field | line | box | image | subreport | special | unknown
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 100.0
    height: float = 14.0
    text: str = ""            # label text
    field_ref: str = ""       # raw Crystal DataSource, e.g. {Orders.AMOUNT}, {@FullName}, {?Branch}
    column: str = ""          # resolved PRD column/expression name
    value_type: str = ""      # Crystal ValueType of the underlying field, if known
    align: str = ""           # left | center | right | justify | ""
    font: Font = field(default_factory=Font)
    notes: list = field(default_factory=list)


@dataclass
class Section:
    area_kind: str            # ReportHeader | PageHeader | GroupHeader | Detail | GroupFooter | ReportFooter | PageFooter
    name: str = ""
    height: float = 20.0
    group_index: int = -1     # which group a GroupHeader/GroupFooter belongs to
    elements: list = field(default_factory=list)
    suppressed: bool = False


@dataclass
class Formula:
    name: str                 # Crystal name without {@}
    text: str                 # original Crystal formula text
    translation: str = ""     # OpenFormula text (with leading =) when translated
    status: str = "manual"    # auto | review | manual
    notes: list = field(default_factory=list)


@dataclass
class Parameter:
    name: str
    value_type: str = "StringField"
    prompt: str = ""
    default: str = ""


@dataclass
class Summary:
    name: str                 # display name, e.g. "Sum of Orders.AMOUNT"
    operation: str            # Sum | Count | Average | Maximum | Minimum | DistinctCount
    field_ref: str = ""       # {Table.Field}
    group_field: str = ""     # group condition column, "" = grand total
    expression_name: str = "" # generated PRD function name


@dataclass
class Group:
    condition_field: str      # raw {Table.Field}
    column: str = ""          # resolved column name
    name: str = ""


@dataclass
class PageSetup:
    paper: str = "LETTER"
    orientation: str = "portrait"
    margin_top: float = 18.0
    margin_left: float = 18.0
    margin_bottom: float = 18.0
    margin_right: float = 18.0


@dataclass
class ReportModel:
    name: str = "Converted Report"
    sql: str = ""             # command SQL if the report used one, else generated
    sql_generated: bool = False
    jndi: str = "SampleData"
    record_selection: str = ""
    tables: dict = field(default_factory=dict)       # table name -> {field name -> ValueType}
    field_types: dict = field(default_factory=dict)  # bare column name -> ValueType
    sections: list = field(default_factory=list)
    formulas: dict = field(default_factory=dict)     # name -> Formula
    parameters: list = field(default_factory=list)
    summaries: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    page: PageSetup = field(default_factory=PageSetup)
    issues: list = field(default_factory=list)       # global conversion warnings

    def sections_of(self, kind: str, group_index: int = -1):
        return [s for s in self.sections
                if s.area_kind == kind and (group_index < 0 or s.group_index == group_index)]

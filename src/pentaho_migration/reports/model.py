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
# Crystal summary FIELDS are group totals: they read correctly in the group
# HEADER too (a letter variant chooses itself by "Sum(...) <> 0" before any
# detail row has printed), so they map to the Total* family, which the engine
# precomputes per group. Running totals ({#name}) genuinely accumulate row by
# row and use the Item* family instead - see RUNNING_CLASS_MAP.
SUMMARY_CLASS_MAP = {
    "Sum": "org.pentaho.reporting.engine.classic.core.function.TotalGroupSumFunction",
    "Count": "org.pentaho.reporting.engine.classic.core.function.TotalGroupCountFunction",
    "Average": "org.pentaho.reporting.engine.classic.core.function.ItemAvgFunction",
    "Maximum": "org.pentaho.reporting.engine.classic.core.function.TotalItemMaxFunction",
    "Minimum": "org.pentaho.reporting.engine.classic.core.function.TotalItemMinFunction",
    "DistinctCount": "org.pentaho.reporting.engine.classic.core.function.CountDistinctFunction",
}

RUNNING_CLASS_MAP = {
    "Sum": "org.pentaho.reporting.engine.classic.core.function.ItemSumFunction",
    "Count": "org.pentaho.reporting.engine.classic.core.function.ItemCountFunction",
    "Average": "org.pentaho.reporting.engine.classic.core.function.ItemAvgFunction",
    "Maximum": "org.pentaho.reporting.engine.classic.core.function.ItemMaxFunction",
    "Minimum": "org.pentaho.reporting.engine.classic.core.function.ItemMinFunction",
    "DistinctCount": "org.pentaho.reporting.engine.classic.core.function.CountDistinctFunction",
}

# Crystal summary operations with NO PRD report function but a standard SQL
# window aggregate: folded into the report SQL as a computed column
# (FUNC(col) OVER (PARTITION BY group)) that the footer field binds to.
# Crystal's StdDev/Variance are the SAMPLE variants (N-1). Dialect note:
# PostgreSQL/Oracle/MySQL 8 use these names; SQL Server uses STDEV/VAR.
WINDOW_AGG_MAP = {
    "StdDeviation": "STDDEV_SAMP",
    "Variance": "VAR_SAMP",
    "PopStandardDeviation": "STDDEV_POP",
    "PopVariance": "VAR_POP",
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
    text_template: str = ""   # PRD message template when the text embeds
                              # field references: "Total due is $(AMOUNT)"
    field_ref: str = ""       # raw Crystal DataSource, e.g. {Orders.AMOUNT}, {@FullName}, {?Branch}
    column: str = ""          # resolved PRD column/expression name
    value_type: str = ""      # Crystal ValueType of the underlying field, if known
    format_string: str = ""   # explicit PRD format override (resolved by field type)
    format_numeric: str = ""  # candidate numeric format from the extractor
    format_date: str = ""     # candidate date format from the extractor
    align: str = ""           # left | center | right | justify | ""
    valign: str = ""          # top | middle | bottom | ""
    font: Font = field(default_factory=Font)
    bg_color: str = ""        # #rrggbb fill behind the element / box fill
    border_color: str = ""    # #rrggbb
    border_width: float = 0.0 # points; 0 = no border
    border_sides: tuple = ()  # sides that carry a line, e.g. ('bottom',); Crystal borders are per-side
    image_bytes: bytes = b""  # embedded raster for kind="image"
    image_mime: str = ""      # image/png | image/jpeg
    resource_path: str = ""   # bundle path assigned by the writer for the image
    visible: bool = True       # Crystal object-level suppression
    can_grow: bool = False     # Crystal "can grow" -> PRD dynamic height
    chart_type: str = ""       # bar | line | area | pie (kind="chart")
    chart_title: str = ""
    chart_category: str = ""   # resolved category column
    chart_series: str = ""     # resolved series column (optional)
    chart_value: str = ""      # resolved value column
    chart_values: list = field(default_factory=list)  # (value column, series label) pairs when one chart plots several series
    chart_extra: dict = field(default_factory=dict)  # authored expression props the render depends on (maxBubbleSize)
    chart_xy: list = field(default_factory=list)  # XY-family series: dicts with series/x/y (+z bubble, time+value+period time-series)
    chart_title_literal: bool = False  # chart_title is authored (even empty) - do not invent one
    chart_category_axis_label: str = ""
    chart_value_axis_label: str = ""
    emit_name: bool = False    # write the element's name into the bundle (a report function targets it)
    crosstab_rows: list = field(default_factory=list)      # row dimension columns (kind="crosstab")
    crosstab_columns: list = field(default_factory=list)   # column dimension columns
    crosstab_summaries: list = field(default_factory=list) # (measure column, Crystal op)
    condition_formulas: list = field(default_factory=list)  # raw (attr, crystal_text)
    style_expressions: list = field(default_factory=list)   # converted (style_key, openformula)
    subreport: object = None       # attached child ReportModel (kind="subreport")
    subreport_links: list = field(default_factory=list)  # (master_column, child_param)
    subreport_href: str = ""       # bundle path assigned by the writer
    notes: list = field(default_factory=list)


def is_todo_element(el) -> bool:
    """True when this element remains manual work after conversion.
    Images whose bytes were migrated into the bundle are converted work,
    not TODOs - only byte-less images (extractor couldn't reach the RAS
    picture data) still need a hand. Same for subreports: one with an
    attached child model converts into a nested PRD sub-report. A
    kind="crosstab" element is always converted work - a cross-tab whose
    definition is missing or unsupported stays kind="unknown"."""
    if el.kind == "subreport":
        return el.subreport is None
    if el.kind == "unknown":
        return True
    return el.kind == "image" and not el.image_bytes and not el.resource_path


# Crystal cross-tab summary operation -> the wizard:aggregation-type string
# PRD's own bundle writer emits for the matching Item*Function (discovered by
# generating reference bundles through the engine - see tools/CrosstabRef.java).
CROSSTAB_AGG_MAP = {
    "Sum": "Sum (Running)",
    "Count": "Count (Running)",
    "Average": "Average (Running)",
    "Maximum": "Maximum (Running)",
    "Minimum": "Minimum (Running)",
}


@dataclass
class Section:
    area_kind: str            # ReportHeader | PageHeader | GroupHeader | Detail | GroupFooter | ReportFooter | PageFooter
    name: str = ""
    height: float = 20.0
    group_index: int = -1     # which group a GroupHeader/GroupFooter belongs to
    elements: list = field(default_factory=list)
    suppressed: bool = False
    bg_color: str = ""        # #rrggbb band background
    condition_formulas: list = field(default_factory=list)  # raw (attr, crystal_text)
    style_expressions: list = field(default_factory=list)   # converted (style_key, openformula)
    new_page_after: bool = False  # Crystal EnableNewPageAfter -> PRD pagebreak-after
    underlay: bool = False    # Crystal EnableUnderlaySection: paints BEHIND following sections
    suppress_if_blank: bool = False  # Crystal EnableSuppressIfBlank: collapse when nothing prints
    # Crystal EnableKeepTogether: the band moves to the next page
    # rather than splitting across one. Without it a statement broke
    # halfway down its invoice table where the original broke after
    # the letter.
    keep_together: bool = False


@dataclass
class Formula:
    name: str                 # Crystal name without {@}
    text: str                 # original Crystal formula text
    value_type: str = ""      # declared Crystal result type (for formats)
    rewrite_class: str = ""   # PRD function class when rewritten (e.g. ItemSumFunction)
    rewrite_field: str = ""   # the field the rewritten function aggregates
    rewrite_group: str = ""   # optional group scope for the rewritten function
    translation: str = ""     # OpenFormula text (with leading =) when translated
    status: str = "manual"    # auto | review | manual
    source: str = "rules"     # rules | llm - who produced the translation
    llm_confidence: str = ""  # the LLM's self-reported confidence (high/medium/low)
    notes: list = field(default_factory=list)

    def prd_target(self) -> str:
        """What this formula became on the PRD side, for display: the
        OpenFormula translation, or the generated report function."""
        if self.translation:
            return self.translation
        if self.rewrite_class:
            kind = self.rewrite_class.rsplit(".", 1)[-1]
            args = []
            if self.rewrite_field:
                args.append(f"field: {self.rewrite_field}")
            if self.rewrite_group:
                args.append(f"group: {self.rewrite_group}")
            return f"{self.name} = {kind}({', '.join(args)})"
        return ""


@dataclass
class Parameter:
    name: str
    value_type: str = "StringField"
    prompt: str = ""
    default: str = ""
    multi_value: bool = False       # Crystal EnableAllowMultipleValue
    optional: bool = False          # Crystal IsOptionalPrompt (optional => not mandatory)
    default_values: list = field(default_factory=list)  # LOV / pick-list values


@dataclass
class Summary:
    name: str                 # display name, e.g. "Sum of Orders.AMOUNT"
    operation: str            # Sum | Count | Average | Maximum | Minimum | DistinctCount
    field_ref: str = ""       # {Table.Field}
    group_field: str = ""     # group condition column, "" = grand total
    expression_name: str = "" # generated PRD function name
    running: bool = False     # {#running total}: row-by-row Item* semantics
    # Crystal PercentOfSum: this group's share of a WIDER total. None means
    # an ordinary summary; "" means the share of the report's grand total,
    # otherwise the outer group whose sum is the denominator.
    percent_of: str | None = None


@dataclass
class TopN:
    """Crystal's Group Sort Expert / Top-N on a group: keep the N groups with
    the largest (Top-N) or smallest (Bottom-N) ranking measure and roll the
    rest into a single "Others" bucket.

    PRD has no Top-N group, so this is realized in the report SQL. RptToXml
    exposes only the direction (TopNOrder/BottomNOrder) and the ranking measure
    - NOT the N count or the "Others" options - so `n`/`others` are assumed and
    flagged for the consultant to confirm (n_assumed)."""
    op: str = "Sum"           # ranking aggregate: Sum, Average, Count, Max, Min
    measure: str = ""         # bare column the measure aggregates
    descending: bool = True   # Top-N = largest first; Bottom-N = smallest
    n: int = 5                # groups kept before "Others"; ASSUMED, not exported
    n_assumed: bool = True
    others: bool = True       # roll the rest into one "Others" bucket
    others_label: str = "Others"


@dataclass
class Group:
    condition_field: str      # raw {Table.Field}
    column: str = ""          # resolved column name
    name: str = ""
    descending: bool = False  # group direction from the SortField list
    topn: object = None       # TopN spec when Group Sort Expert / Top-N is used


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
    # Target SQL dialect for the few places a formula must become a query
    # column (a cross-tab dimension computed in the report). Defaults to the
    # sample databases' engine; see reports/formula_sql.py.
    sql_dialect: str = "mysql"
    record_selection: str = ""
    definition_format: str = ""  # simple | legacy-ext: which old JFreeReport dialect the layout came from
    record_selection_folded: bool = False  # True when folded into the SQL WHERE
    # Keyed by the table's ALIAS - the name every field reference, formula
    # and table link is written against. See _parse_database.
    tables: dict = field(default_factory=dict)       # table alias -> {field name -> ValueType}
    # alias -> where the data physically came from, when it differs: a real
    # table name for a database, an XPath for an XML file
    table_sources: dict = field(default_factory=dict)
    field_types: dict = field(default_factory=dict)  # bare column name -> ValueType
    field_formats: dict = field(default_factory=dict)  # bare column -> numeric format ("$#,##0.00")
    sections: list = field(default_factory=list)
    formulas: dict = field(default_factory=dict)     # name -> Formula
    parameters: list = field(default_factory=list)
    summaries: list = field(default_factory=list)
    port_functions: list = field(default_factory=list)  # (name, java class, {prop: value}) legacy functions PRD still ships, emitted verbatim
    groups: list = field(default_factory=list)
    record_sorts: list = field(default_factory=list)  # (bare column, descending) detail ordering
    saved_rows: object = None  # rpt_saved.SavedRows recovered from the .rpt binary, or None
    table_links: list = field(default_factory=list)   # ((table, col), (table, col)) visual links
    param_sql_columns: dict = field(default_factory=dict)  # param name -> folded SQL column expr
    param_lov_sql: dict = field(default_factory=dict)  # param name -> (lookup sql, key col, display col): a pick-list feed carried as its own query
    window_columns: list = field(default_factory=list)  # (alias, sql func, column, group column) folded window aggregates
    subreports: dict = field(default_factory=dict)    # subreport name -> child ReportModel
    page: PageSetup = field(default_factory=PageSetup)
    issues: list = field(default_factory=list)       # global conversion warnings

    def sections_of(self, kind: str, group_index: int = -1):
        return [s for s in self.sections
                if s.area_kind == kind and (group_index < 0 or s.group_index == group_index)]

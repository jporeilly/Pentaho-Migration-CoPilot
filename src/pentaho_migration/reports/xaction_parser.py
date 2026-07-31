"""Parse a Pentaho BI-platform action sequence (`.xaction`) and build a
ReportModel from its report pipeline.

An xaction is orchestration XML: inputs (parameters), resources (the old
JFreeReport definition), and an ordered chain of components. For a REPORT
xaction the chain is typically lookups (SQL/MDX/XQuery) -> prompts
(SecureFilterComponent) -> JFreeReportComponent, with JavascriptRule /
TemplateComponent / EmailComponent orchestration around it. The conversion:

  * the lookup that FEEDS the report      -> the .prpt query ({PREPARE:x} -> ${x})
  * SecureFilter selections               -> .prpt parameters; a selection fed
                                             by another lookup is a
                                             query-backed pick-list
  * the paired JFreeReport definition     -> layout (jfreereport_parser)
  * everything else                       -> a suggested-solution note, per the
                                             product's core principle

The same scan yields a deterministic COMPLEXITY grade (Low / Medium / High)
with its reasons - the per-report Level-of-Effort signal a T&M estimate needs.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from pentaho_migration.reports.model import Parameter, ReportModel

_LOOKUP_COMPONENTS = ("SQLLookupRule", "MDXLookupRule", "XQueryLookupRule")


@dataclass
class XInput:
    name: str
    value_type: str = "string"
    default: str = ""
    has_default: bool = False   # a <default-value/> node exists, even empty:
                                # the platform accepts a blank value, so the
                                # PRD parameter is OPTIONAL, not mandatory
    list_maps: list = field(default_factory=list)  # property-map-list rows:
                                # [{entry-key: text}] - a STATIC pick-list
                                # hardcoded in the xaction inputs


@dataclass
class XAction:
    """One action-definition: the component, its bindings, its definition."""
    component: str
    action_type: str = ""
    inputs: list = field(default_factory=list)     # (name, type, mapping)
    outputs: list = field(default_factory=list)    # (name, type, mapping)
    resources: list = field(default_factory=list)  # (name, type, mapping)
    definition: object = None                      # the component-definition node
    in_loop: bool = False                          # nested in an action loop

    def deftext(self, tag: str) -> str:
        if self.definition is None:
            return ""
        node = self.definition.find(tag)
        return (node.text or "").strip() if node is not None else ""


@dataclass
class XActionModel:
    name: str = ""
    title: str = ""
    inputs: list = field(default_factory=list)     # [XInput]
    resources: dict = field(default_factory=dict)  # resource name -> location
    actions: list = field(default_factory=list)    # [XAction]

    @property
    def report_actions(self):
        return [a for a in self.actions if a.component == "JFreeReportComponent"]

    @property
    def is_report(self) -> bool:
        return bool(self.report_actions)

    def lookups(self):
        return [a for a in self.actions if a.component in _LOOKUP_COMPONENTS]


def _bindings(node, container_tag):
    out = []
    container = node.find(container_tag)
    if container is not None:
        for child in container:
            out.append((child.tag, child.get("type") or "",
                        child.get("mapping") or child.tag))
    return out


def parse_xaction(source) -> XActionModel:
    data = (Path(source).read_bytes()
            if not isinstance(source, (bytes, bytearray)) else bytes(source))
    root = ET.fromstring(data)
    if root.tag != "action-sequence":
        raise ValueError(f"not an action sequence (root <{root.tag}>)")

    model = XActionModel(name=(root.findtext("name") or "").strip(),
                         title=(root.findtext("title") or "").strip())

    inputs = root.find("inputs")
    if inputs is not None:
        for node in inputs:
            maps = [
                {e.get("key"): (e.text or "").strip() for e in pm.iter("entry")}
                for pm in node.iter("property-map")]
            model.inputs.append(XInput(
                name=node.tag, value_type=node.get("type") or "string",
                default=(node.findtext("default-value") or "").strip()
                if not maps else "",
                has_default=node.find("default-value") is not None,
                list_maps=maps))

    resources = root.find("resources")
    if resources is not None:
        for node in resources:
            loc = node.findtext("./solution-file/location")
            if loc:
                model.resources[node.tag] = loc.strip()

    def walk(node, in_loop):
        for child in node:
            if child.tag == "action-definition":
                model.actions.append(XAction(
                    component=(child.findtext("component-name") or "").strip(),
                    action_type=(child.findtext("action-type") or "").strip(),
                    inputs=_bindings(child, "action-inputs"),
                    outputs=_bindings(child, "action-outputs"),
                    resources=_bindings(child, "action-resources"),
                    definition=child.find("component-definition"),
                    in_loop=in_loop))
            elif child.tag in ("actions", "action-loop"):
                walk(child, in_loop or child.tag == "action-loop"
                     or child.get("loop-on") is not None)
    actions_node = root.find("actions")
    if actions_node is not None:
        walk(root, False)
    return model


def _selections(action):
    """SecureFilterComponent selections: (param, title, style, list_source,
    value_col, display_col). `list_source` is the binding a pick-list feed
    arrives on - the OUTPUT of an earlier lookup for query-backed lists."""
    out = []
    if action.definition is None:
        return out
    sel_container = action.definition.find("selections")
    if sel_container is None:
        return out
    for sel in sel_container:
        filt = sel.find("filter")
        out.append((
            sel.tag,
            (sel.findtext("title") or "").strip(),
            sel.get("style") or "select",
            (filt.text or "").strip() if filt is not None else "",
            filt.get("value-col-name") if filt is not None else "",
            filt.get("display-col-name") if filt is not None else "",
        ))
    return out


def classify_complexity(x: XActionModel):
    """Deterministic Low/Medium/High from the xaction's own structure - the
    per-report Level-of-Effort signal. Pick-list lookups (those feeding
    prompts) are cheap and do not count as extra data sources."""
    reports = x.report_actions
    lookups = x.lookups()
    prompt_feeds = set()
    prompts = 0
    for a in x.actions:
        if a.component == "SecureFilterComponent":
            sels = _selections(a)
            prompts += len(sels)
            prompt_feeds.update(s[3] for s in sels if s[3])
    data_lookups = [a for a in lookups
                    if not any(o[0] in prompt_feeds or o[2] in prompt_feeds
                               for o in a.outputs)]
    has_email = any(a.component == "EmailComponent" for a in x.actions)
    has_js = any(a.component == "JavascriptRule" for a in x.actions)
    has_mdx = any(a.component == "MDXLookupRule" for a in data_lookups)
    has_xquery = any(a.component == "XQueryLookupRule" for a in data_lookups)
    bursting = has_email or any(a.in_loop for a in reports) or len(reports) >= 2

    reasons = []
    if bursting:
        reasons.append("bursting/distribution (email or looped renders)")
    if len(reports) >= 2:
        reasons.append(f"{len(reports)} report renders")
    if has_mdx:
        reasons.append("MDX (Mondrian) data source")
    if has_xquery:
        reasons.append("XQuery/XML data source")
    if len(data_lookups) >= 2:
        reasons.append(f"{len(data_lookups)} data queries")
    if has_js:
        reasons.append("JavaScript business logic")
    if prompts:
        reasons.append(f"{prompts} prompt(s)")

    if bursting or len(data_lookups) >= 3 or (has_mdx and len(lookups) > 1):
        return "High", reasons
    if has_js or prompts or len(data_lookups) >= 2 or has_mdx or has_xquery:
        return "Medium", reasons
    return "Low", reasons or ["single query straight into the report"]


_PREPARE = re.compile(r"\{PREPARE:\s*([^}\s]+)\s*\}")
_PLACEHOLDER = re.compile(r"^\$\{(\w+)\}$")


def _select_columns(sql: str):
    """The output columns of the feeding SELECT: [(alias, is_aggregate)].
    Top-level comma split between SELECT and FROM; an item containing a
    parenthesis is an aggregate/expression."""
    m = re.search(r"\bSELECT\b(.*?)\bFROM\b", sql or "", re.I | re.S)
    if not m:
        return []
    items, depth, cur = [], 0, ""
    for ch in m.group(1):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        items.append(cur)
    out = []
    for item in items:
        alias = re.search(r'\bAS\s+"?([A-Za-z_]\w*)"?\s*$', item.strip(), re.I)
        name = (alias.group(1) if alias
                else (re.findall(r"([A-Za-z_]\w*)\s*$", item.strip()) or [""])[0])
        if name:
            out.append((name, "(" in item))
    return out


def _resolve_templated_bindings(model, x) -> None:
    """Resolve `${name}` field bindings left in a shared report definition.
    Order: an xaction input's default value (the platform's own substitution),
    then type-uniqueness against the query (exactly one aggregate column for a
    number-field, exactly one plain column for a string-field). Unresolved
    bindings stay honest TODOs."""
    ph_elements = [el for s in model.sections for el in s.elements
                   if el.kind == "field" and _PLACEHOLDER.match(el.column or "")]
    ph_summaries = [s for s in model.summaries if "${" in (s.field_ref or "")]
    if not ph_elements and not ph_summaries:
        return
    cols = _select_columns(model.sql)
    plain = [a for a, agg in cols if not agg]
    aggs = [a for a, agg in cols if agg]
    input_defaults = {i.name: i.default for i in x.inputs if i.default}
    resolved: dict = {}
    for el in ph_elements:
        name = _PLACEHOLDER.match(el.column).group(1)
        target = resolved.get(name) or input_defaults.get(name)
        if not target:
            if el.value_type == "NumberField" and len(aggs) == 1:
                target = aggs[0]
            elif el.value_type == "StringField" and len(plain) == 1:
                target = plain[0]
        if target:
            resolved[name] = target
            el.column = target
            model.field_types.setdefault(target, el.value_type)
        else:
            el.notes.append(
                f"field bound to the template placeholder '${{{name}}}' - the "
                "platform substituted it from context this sequence does not "
                "define; bind it to the query column it stands for")
    for summ in ph_summaries:
        for name, target in resolved.items():
            summ.field_ref = summ.field_ref.replace(f"${{{name}}}", target)
    if resolved:
        model.issues.append(
            "templated field binding(s) resolved from the query's own shape: "
            + ", ".join(f"'${{{n}}}' -> {t}" for n, t in sorted(resolved.items()))
            + " - the platform substituted these from context the sequence "
            "does not define; review the binding")


def build_report_model(xaction_source, resolver=None) -> ReportModel:
    """xaction -> ReportModel, layout from its paired report definition.

    `resolver(location) -> bytes` loads a resource by its solution-file
    location; the default resolves siblings of the .xaction file."""
    from pentaho_migration.reports.jfreereport_parser import parse_jfreereport

    path = None
    if not isinstance(xaction_source, (bytes, bytearray)):
        path = Path(xaction_source)
    x = parse_xaction(xaction_source)
    if not x.is_report:
        comps = sorted({a.component for a in x.actions})
        model = ReportModel(name=x.name or "xaction")
        model.issues.append(
            "this action sequence has no JFreeReportComponent - it is not a "
            f"report (components: {', '.join(comps)}). A chart/dashboard "
            "xaction becomes a CDE/CDF dashboard or a PRD chart report; a "
            "Kettle xaction is ETL - convert it on the PDI side.")
        return model

    if resolver is None:
        base = path.parent if path else Path(".")

        def resolver(location):
            return (base / Path(location).name).read_bytes()

    report_action = x.report_actions[0]

    # ---- layout: the paired old JFreeReport definition -------------------
    # The component may name its resource explicitly (action-resources
    # mapping) or rely on the platform convention: a resource called
    # report-definition (optionally suffixed) binds implicitly.
    res_ref = next((m for _n, _t, m in report_action.resources), None)
    location = x.resources.get(res_ref or "", "")
    if not location:
        location = next((loc for name, loc in x.resources.items()
                         if name.startswith("report-definition")), "")
    model = ReportModel()
    if location:
        try:
            model = parse_jfreereport(resolver(location))
        except FileNotFoundError:
            model.issues.append(
                f"report definition {location!r} was not uploaded with the "
                ".xaction - upload the paired report XML from the same "
                "solution folder to convert the layout")
        except ET.ParseError as exc:
            model.issues.append(
                f"report definition {location!r} did not parse ({exc}) - "
                "the layout must be rebuilt by hand")
    else:
        model.issues.append(
            "the xaction names no report-definition resource (the definition "
            "may be inline or generated) - the layout must come from the "
            "original solution folder")
    model.name = x.title if x.title and not x.title.startswith("%") else \
        (Path(x.name).stem if x.name else model.name)

    # ---- datasource: the lookup that feeds the report --------------------
    data_binding = next((m for n, t, m in report_action.inputs
                         if t == "result-set"), None)
    feed = None
    for a in x.lookups():
        if any(n == data_binding or m == data_binding
               for n, _t, m in a.outputs):
            feed = a
    if feed is None and x.lookups():
        feed = x.lookups()[-1]

    if feed is not None:
        if feed.component == "SQLLookupRule":
            sql = _PREPARE.sub(r"${\1}", feed.deftext("query"))
            # Bare {name} placeholders (no PREPARE) are DYNAMIC SQL fragments
            # the platform text-substituted - usually built by the sequence's
            # JavaScript ("AND col = 'x'", or empty for the 'default' prompt
            # choice). Removing them runs the query as its default, unfiltered
            # case - exactly what the xaction's own defaults produce - and the
            # note says how to keep the prompt-driven filter.
            fragments = sorted(set(re.findall(r"(?<!\$)\{([A-Za-z_]\w*)\}", sql)))
            if fragments:
                sql = re.sub(r"(?<!\$)\{[A-Za-z_]\w*\}", "", sql)
                model.issues.append(
                    "dynamic SQL fragment(s) "
                    + ", ".join(f"'{{{f}}}'" for f in fragments)
                    + " were text-substituted by the platform (built by the "
                    "sequence's JavaScript) - removed so the query runs its "
                    "DEFAULT unfiltered case; to keep each prompt's filter, "
                    "add its clause with a ${param} (e.g. AND OFFICES.TERRITORY "
                    "= ${territory}) per the script logic in these notes")
            model.sql = sql
            model.jndi = feed.deftext("jndi") or model.jndi
        elif feed.component == "MDXLookupRule":
            mdx = feed.deftext("query") or feed.deftext("mdx")
            model.issues.append(
                "the report reads an MDX (Mondrian) query - PRD supports a "
                "Mondrian datasource natively: create it against the same "
                "catalog, paste the MDX, and keep the field names. Query "
                f"carried in the conversion report: {mdx[:160]}...")
        elif feed.component == "XQueryLookupRule":
            model.issues.append(
                "the report reads an XQuery/XML source - use PRD's XML/XPath "
                "datasource against the same document; the field names carry over")

    # ---- parameters: xaction inputs + SecureFilter prompts ---------------
    prompts = {}
    picklist_feeds = {}
    for a in x.actions:
        if a.component != "SecureFilterComponent":
            continue
        for pname, title, style, list_source, vcol, dcol in _selections(a):
            prompts[pname] = (title, style, list_source, vcol, dcol)
            if list_source:
                picklist_feeds[list_source] = pname
    lookup_by_output = {}
    for a in x.lookups():
        for n, _t, m in a.outputs:
            lookup_by_output[n] = a
            lookup_by_output[m] = a

    used = set(_PREPARE.findall(feed.deftext("query"))) if feed is not None else set()
    for inp in x.inputs:
        if inp.name not in used and inp.name not in prompts:
            continue
        title, style, list_source, vcol, dcol = prompts.get(
            inp.name, ("", "", "", "", ""))
        prm = Parameter(name=inp.name, prompt=title or inp.name,
                        default=inp.default, optional=inp.has_default)
        # The old platform TEXT-substituted parameter strings into the SQL and
        # HSQLDB 1.8 cast a bare date leniently; PRD binds a JDBC string and
        # HSQLDB 2.x only implicitly converts the FULL timestamp format. A
        # date-only default is padded to midnight so the comparison still
        # works; a non-ISO default is the original's own defect - flagged.
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", inp.default or ""):
            prm.default = f"{inp.default} 00:00:00"
            model.issues.append(
                f"date parameter '{inp.name}' default padded to "
                f"'{prm.default}' - HSQLDB 2.x converts only the full "
                "timestamp format; pick-list values may need the same padding")
        elif re.fullmatch(r"\d{2}-\d{2}-\d{4}", inp.default or ""):
            model.issues.append(
                f"parameter '{inp.name}' default {inp.default!r} is not ISO "
                "(dd-mm-yyyy?) - the database will reject it; fix the default "
                "to yyyy-mm-dd hh:mm:ss")
        src = lookup_by_output.get(list_source)
        list_input = next((i for i in x.inputs
                           if i.name == list_source and i.list_maps), None)
        if src is not None and src.component == "SQLLookupRule":
            q = src.deftext("query")
            model.issues.append(
                f"parameter '{inp.name}' prompts from a query pick-list "
                f"(display {dcol!r}, value {vcol!r}) - recreate it as a PRD "
                "query-backed list parameter with the same query: "
                + " ".join(q.split())[:180])
        elif list_input is not None:
            # a STATIC pick-list hardcoded in the xaction inputs - carries
            # straight into a PRD list-parameter (LOV)
            prm.default_values = [m.get(vcol, "") for m in list_input.list_maps
                                  if m.get(vcol)]
        model.parameters.append(prm)

    # ---- templated field bindings ----------------------------------------
    # Some shared definitions bind fields to ${name} placeholders the platform
    # substituted from context (Sales_by_*: ${Group_by}/${Amount}). When the
    # sequence itself defines the name (an input default), that is the value;
    # otherwise the query's own shape can settle it DETERMINISTICALLY when
    # unambiguous: one aggregate column for a number-field, one plain column
    # for a string-field. Anything still open stays an honest TODO.
    _resolve_templated_bindings(model, x)

    # ---- orchestration components -> suggested solutions -----------------
    for a in x.actions:
        if a.component == "JavascriptRule":
            script = " ".join(a.deftext("script").split())[:140]
            model.issues.append(
                "JavaScript business logic in the action sequence - fold it "
                "into the SQL as a computed column, or a PRD function/"
                f"formula. Script head: {script}")
        elif a.component == "EmailComponent":
            model.issues.append(
                "the sequence EMAILS the rendered report (bursting/"
                "distribution) - the render converts to .prpt; schedule and "
                "distribute it with a PDI job (Get rows -> loop -> Pentaho "
                "Reporting output -> Mail) or the Pentaho Server scheduler")
        elif a.component == "TemplateComponent":
            model.issues.append(
                "an HTML template wraps the render - PRD owns the whole page "
                "instead; move any wrapper branding into the report/page "
                "header or the server's HTML export template")
        elif a.component == "UtilityComponent":
            model.issues.append(
                "a UtilityComponent munges variables (copy/format) - platform "
                "plumbing with no .prpt counterpart; its effect usually folds "
                "into the query or a parameter default - verify nothing else "
                "consumed it")
        elif a.component == "ChartComponent" and a is not feed:
            model.issues.append(
                "a ChartComponent renders a chart image beside the report - "
                "recreate it as a PRD chart element bound to the same query")

    grade, reasons = classify_complexity(x)
    model.complexity = grade
    model.complexity_reasons = reasons
    model.issues.append(
        f"complexity: {grade}" + (f" ({'; '.join(reasons)})" if reasons else "")
        + " - the Level-of-Effort signal for a T&M estimate")
    return model


def load_xaction_model(path, jndi: str | None = None) -> ReportModel:
    """Full read side for an .xaction. The Crystal finishing pipeline is NOT
    reused: there are no Crystal formulas to translate, the query is the
    xaction's own command SQL (never generated - fabricating a SELECT for an
    MDX/XQuery feed would be a lie), and Top-N/window folding cannot occur."""
    model = build_report_model(path)
    if jndi:
        model.jndi = jndi
    return model

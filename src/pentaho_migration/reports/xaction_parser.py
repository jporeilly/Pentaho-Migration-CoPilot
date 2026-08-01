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
    inline_resources: dict = field(default_factory=dict)  # name -> XML bytes embedded IN the xaction (WAQR)
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
                continue
            # WAQR embeds the whole definition INLINE:
            # <resource><xml><location><report ...> - the location holds
            # a document, not a path
            xml_node = node.find("./xml/location")
            if xml_node is not None and len(xml_node):
                model.inline_resources[node.tag] = ET.tostring(
                    xml_node[0], encoding="utf-8")

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
_PLACEHOLDER_ANY = re.compile(r"\$\{(\w+)\}")


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


def _repair_nested_comments(text: str):
    """Tolerant repair for the malformations the corpus actually has.

    The billing dashboard's author typed ``->>`` where ``-->`` belongs,
    so the comment never closed and the next ``<!--`` nested (illegal).
    Repair order inside an open comment: a TYPO'D closer (``->>``,
    ``- ->``, ``--!>``) becomes ``-->`` - the comment ends exactly where
    the author meant it to; failing that, the stray comment is closed
    just before the next ``<!--``; an EOF inside a comment gets a
    closer appended. Returns the repaired text, or None if nothing
    needed repair."""
    typo = re.compile(r"-\s?->>|->>|--!>|-\s->")
    out = []
    pos = 0
    in_comment = False
    changed = False
    while True:
        if not in_comment:
            i = text.find("<!--", pos)
            if i == -1:
                out.append(text[pos:])
                break
            out.append(text[pos:i + 4])
            pos = i + 4
            in_comment = True
        else:
            close = text.find("-->", pos)
            nxt = text.find("<!--", pos)
            m = typo.search(text, pos)
            candidates = [c for c in (
                ("close", close), ("open", nxt),
                ("typo", m.start() if m else -1)) if c[1] != -1]
            if not candidates:
                out.append(text[pos:] + " -->")
                changed = True
                break
            kind, at = min(candidates, key=lambda c: c[1])
            if kind == "close":
                out.append(text[pos:at + 3])
                pos = at + 3
                in_comment = False
            elif kind == "typo":
                out.append(text[pos:at] + "-->")
                pos = m.end()
                in_comment = False
                changed = True
            else:
                out.append(text[pos:at] + " -->")
                pos = at
                in_comment = False
                changed = True
    return "".join(out) if changed else None


def _scripted_values(x):
    """Evaluate every JavascriptRule over the sequence's own input
    defaults through the safe JS-subset interpreter (js_eval). Returns
    ``(values, script_states)``:

    * ``values`` - {output name: string} for every output the scripts
      assigned; exact, because the interpreter runs the same statement
      prefix the platform ran.
    * ``script_states`` - one entry per script:
      ``(action, evaluated outputs, stopped_at fragment or None)`` so
      the note pass can say per script whether it was fully computed,
      partially computed, or why it stayed manual.
    """
    from pentaho_migration.reports.js_eval import evaluate_script

    inputs = {}
    for inp in x.inputs:
        if inp.default in (None, ""):
            continue
        try:
            text = str(inp.default)
            inputs[inp.name] = (float(text) if "." in text else int(text))
        except (TypeError, ValueError):
            inputs[inp.name] = str(inp.default)

    values = {}
    script_states = []
    for a in x.actions:
        if a.component != "JavascriptRule":
            continue
        declared = [n for n, _t, _m in a.outputs]
        script = a.deftext("script") or ""
        got, stopped = evaluate_script(script, {**inputs, **values},
                                       declared)
        values.update(got)
        script_states.append((a, got, stopped))
    return values, script_states


def _resolve_templated_bindings(model, x, derived=None) -> None:
    """Resolve `${name}` field bindings left in a shared report definition.
    Order: an xaction input's default value (the platform's own substitution),
    then type-uniqueness against the query (exactly one aggregate column for a
    number-field, exactly one plain column for a string-field). Unresolved
    bindings stay honest TODOs."""
    ph_elements = [el for s in model.sections for el in s.elements
                   if el.kind == "field" and _PLACEHOLDER.match(el.column or "")]
    ph_summaries = [s for s in model.summaries if "${" in (s.field_ref or "")]
    ph_other = any(
        "${" in (s.name + s.expression_name) for s in model.summaries
    ) or any(
        "${" in (el.chart_category + el.chart_value + el.chart_series
                 + "".join(c + n for c, n in el.chart_values))
        for sec in model.sections for el in sec.elements
        if el.kind == "chart"
    ) or any(
        "${" in f for sec in model.sections for el in sec.elements
        for _k, f in el.style_expressions
    ) or any(
        "${" in (el.text + el.text_template)
        for sec in model.sections for el in sec.elements)
    if not ph_elements and not ph_summaries and not ph_other:
        return
    cols = _select_columns(model.sql)
    plain = [a for a, agg in cols if not agg]
    aggs = [a for a, agg in cols if agg]
    input_defaults = {i.name: i.default for i in x.inputs if i.default}
    input_defaults.update(derived or {})
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

    # the same placeholders reach chart bindings, style-expression formulas
    # and summary NAMES (the EXT format templates all three); substitute from
    # what resolved above plus the inputs' own defaults - the same order the
    # platform substituted in
    subs = {**input_defaults, **resolved}

    def _sub(text):
        return _PLACEHOLDER_ANY.sub(
            lambda m: subs.get(m.group(1), m.group(0)), text or "")

    if subs:
        for s in model.summaries:
            s.name = _sub(s.name)
            s.expression_name = _sub(s.expression_name)
            s.field_ref = _sub(s.field_ref)
        for sec in model.sections:
            for el in sec.elements:
                el.text = _sub(el.text)
                el.text_template = _sub(el.text_template)
                if el.kind == "field":
                    el.column = _sub(el.column)
                if el.kind == "chart":
                    el.chart_category = _sub(el.chart_category)
                    el.chart_series = _sub(el.chart_series)
                    el.chart_value = _sub(el.chart_value)
                    el.chart_values = [(_sub(c), _sub(n))
                                       for c, n in el.chart_values]
                el.style_expressions = [(k, _sub(f))
                                        for k, f in el.style_expressions]
    if resolved:
        model.issues.append(
            "templated field binding(s) resolved from the query's own shape: "
            + ", ".join(f"'${{{n}}}' -> {t}" for n, t in sorted(resolved.items()))
            + " - the platform substituted these from context the sequence "
            "does not define; review the binding")


def _stub_missing_queries(model) -> None:
    if not model.sql:
        # a non-SQL feed (MDX/XQuery) leaves the bundle with no runnable
        # query, which would fail outright on open. A typed EMPTY stub over
        # the columns the layout itself references stands in, so the
        # converted layout opens, renders and can be reviewed; the datasource
        # note above says how to wire the real feed back.
        columns = {}
        for sec in model.sections:
            for el in sec.elements:
                if el.kind == "field" and el.column:
                    columns.setdefault(
                        el.column, el.value_type in ("NumberField",
                                                     "CurrencyField"))
                if el.kind == "chart":
                    for col, _label in (el.chart_values
                                        or [(el.chart_value, "")]):
                        if col:
                            columns.setdefault(col, True)
                    if el.chart_category:
                        columns.setdefault(el.chart_category, False)
        for summ in model.summaries:
            col = re.sub(r"^\{R\.|\}$", "", summ.field_ref or "")
            if col:
                columns.setdefault(col, True)
        if columns:
            select = ", ".join(
                ("CAST(NULL AS DOUBLE)" if numeric
                 else "CAST(NULL AS VARCHAR(80))") + f' AS "{name}"'
                for name, numeric in columns.items())
            model.sql = (f"SELECT {select}\nFROM (VALUES(0)) AS stub(x)\n"
                         "WHERE 1 = 0")
            model.sql_generated = True
            model.issues.append(
                "a typed empty stub query stands in for the non-SQL feed so "
                "the converted layout opens and renders for review - replace "
                "it with the datasource the note above describes")


    # nested sub-reports carry their own bundles - stub theirs too, and
    # hand down the connection so the child opens against the same source
    for sec in model.sections:
        for el in sec.elements:
            if el.kind == "subreport" and el.subreport is not None:
                child = el.subreport
                child.jndi = child.jndi or model.jndi
                child.sql_dialect = child.sql_dialect or model.sql_dialect
                _stub_missing_queries(child)


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
    # Resolution ladder, most explicit first: the component's own
    # action-resources mapping; a resource picked BY NAME through a
    # `resource-name` input (the chart-types pattern - the platform's own
    # selection, reproduced from the input's default / first pick-list
    # row); the report-definition* naming convention; a definition
    # embedded INLINE in the xaction (WAQR). What resolves may be a
    # file, a jar carrying the definition, or - when the runtime .xml
    # was never committed - the Report Designer 1.x `.report` source
    # beside the xaction.
    res_ref = next((m for _n, _t, m in report_action.resources), None)
    location = x.resources.get(res_ref or "", "")
    resolution_notes = []
    inline_name = res_ref if res_ref in x.inline_resources else ""

    if not location and not inline_name:
        rn_input = next((m for n, _t, m in report_action.inputs
                         if n == "resource-name"), None)
        if rn_input:
            inp = next((i for i in x.inputs if i.name == rn_input), None)
            pick = (inp.default if inp and inp.default else "")
            if not pick:
                for i2 in x.inputs:
                    for pm in i2.list_maps:
                        if pm.get(rn_input):
                            pick = pm[rn_input]
                            break
                    if pick:
                        break
            if pick and pick in x.resources:
                location = x.resources[pick]
                others = sorted(n for n, loc in x.resources.items()
                                if n != pick and loc.endswith(".xml"))
                resolution_notes.append(
                    f"the sequence picks its definition at run time via "
                    f"'{rn_input}' - converted with {pick!r} "
                    f"({location}), the platform's own default choice; "
                    "the alternates convert the same way: "
                    + ", ".join(others[:8]))

    if not location and not inline_name:
        location = next((loc for name, loc in x.resources.items()
                         if name.startswith("report-definition")), "")
    if not location and not inline_name:
        location = next((loc for name, loc in x.resources.items()
                         if name.startswith("report-jar")
                         or loc.lower().endswith(".jar")), "")
    if not location and not inline_name:
        inline_name = next((n for n in x.inline_resources
                            if n.startswith("report-definition")), "")

    def _sibling(name):
        try:
            return resolver(name)
        except Exception:
            return None

    derived, script_states = _scripted_values(x)

    def _parse_definition(data, defaults):
        from pentaho_migration.reports.reportdesigner1_parser import (
            looks_like_designer1, parse_designer1_report)
        if looks_like_designer1(data):
            return parse_designer1_report(data)
        return parse_jfreereport(data, resource_loader=_sibling,
                                 input_defaults=defaults)

    model = ReportModel()
    defaults = {i.name: i.default for i in x.inputs if i.default}
    defaults.update(derived)

    if inline_name:
        data = x.inline_resources[inline_name]
        # WAQR definitions template their headers from parser-config
        # properties (${reportheader}) - the platform substituted them,
        # so conversion does too
        try:
            cfg = ET.fromstring(data).find("parser-config")
            if cfg is not None:
                for prop in cfg.iter("property"):
                    if prop.get("name") and (prop.text or "").strip():
                        derived.setdefault(prop.get("name"),
                                           prop.text.strip())
                        defaults.setdefault(prop.get("name"),
                                            prop.text.strip())
        except ET.ParseError:
            pass
        try:
            model = _parse_definition(data, defaults)
            model.issues.append(
                "the report definition was embedded INLINE in the "
                "xaction (the WAQR ad-hoc pattern) - parsed straight "
                "from the sequence, nothing to upload")
        except ET.ParseError as exc:
            model.issues.append(
                f"the inline report definition did not parse ({exc}) - "
                "the layout must be rebuilt by hand")
    elif location and location.lower().endswith(".jar"):
        jar_bytes = _sibling(location)
        candidate = None
        if jar_bytes and jar_bytes[:2] == b"PK":
            import io
            import zipfile
            with zipfile.ZipFile(io.BytesIO(jar_bytes)) as z:
                for entry in z.namelist():
                    if not entry.lower().endswith(".xml"):
                        continue
                    body = z.read(entry)
                    if b"<report" in body[:2000]:
                        candidate = (entry, body)
                        break
        if candidate:
            entry, body = candidate
            try:
                model = _parse_definition(body, defaults)
                model.issues.append(
                    f"the report definition was extracted from "
                    f"{location!r} (entry {entry!r}) - jar-shipped "
                    "definitions convert like any other")
            except ET.ParseError as exc:
                model.issues.append(
                    f"the definition inside {location!r} did not parse "
                    f"({exc}) - the layout must be rebuilt by hand")
        else:
            model.issues.append(
                f"the report definition ships inside {location!r}, which "
                "was not uploaded with the solution - include the jar "
                "and re-convert (definitions are extracted from jars)")
    elif location:
        try:
            model = _parse_definition(resolver(location), defaults)
        except FileNotFoundError:
            fallback = _sibling(Path(location).stem + ".report")
            if fallback:
                try:
                    model = _parse_definition(fallback, defaults)
                    model.issues.append(
                        f"the runtime definition {location!r} was never "
                        "committed, but its Report Designer 1.x source "
                        f"('{Path(location).stem}.report') sits beside "
                        "the xaction - the layout was recovered from "
                        "the designer source; verify against a rendered "
                        "original if one exists")
                except ET.ParseError:
                    fallback = None
            if not fallback:
                model.issues.append(
                    f"report definition {location!r} was not uploaded "
                    "with the .xaction - upload the paired report XML "
                    "from the same solution folder to convert the layout")
        except ET.ParseError as exc:
            repaired = None
            try:
                raw = resolver(location)
                fixed = _repair_nested_comments(
                    raw.decode("utf-8", "replace"))
                if fixed is not None:
                    repaired = _parse_definition(
                        fixed.encode("utf-8"), defaults)
            except Exception:
                repaired = None
            if repaired is not None:
                model = repaired
                model.issues.append(
                    f"the definition's own XML was malformed ({exc}) - "
                    "an unterminated/nested comment was repaired "
                    "tolerantly (everything between the stray comment "
                    "markers stays commented); review that region "
                    "against the original")
            else:
                model.issues.append(
                    f"report definition {location!r} did not parse "
                    f"({exc}) - the layout must be rebuilt by hand")
    else:
        model.issues.append(
            "the xaction names no report-definition resource (the definition "
            "may be inline or generated) - the layout must come from the "
            "original solution folder")
    model.issues.extend(resolution_notes)
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
            # the platform text-substituted. When the sequence itself defines
            # the value - an input's default, or a line of arithmetic the
            # evaluator computed - substituting it reproduces the platform's
            # own default run. Only a fragment nothing defines is removed
            # (usually an optional clause that is empty in the default case),
            # and the note says how to keep the prompt-driven filter.
            fragments = sorted(set(re.findall(r"(?<!\$)\{([A-Za-z_]\w*)\}", sql)))
            if fragments:
                values = {i.name: i.default for i in x.inputs if i.default}
                values.update(derived)
                filled = sorted(f for f in fragments if values.get(f))
                stripped = sorted(f for f in fragments if not values.get(f))
                for f in filled:
                    sql = sql.replace(f"{{{f}}}", values[f])
                if stripped:
                    sql = re.sub(r"(?<!\$)\{[A-Za-z_]\w*\}", "", sql)
                if filled:
                    model.issues.append(
                        "dynamic SQL fragment(s) "
                        + ", ".join(f"'{{{f}}}' -> {values[f]}" for f in filled)
                        + " substituted with the sequence's own value(s), the "
                        "same text substitution the platform performed - to "
                        "re-parameterise, swap the value back to a ${param}")
                if stripped:
                    model.issues.append(
                        "dynamic SQL fragment(s) "
                        + ", ".join(f"'{{{f}}}'" for f in stripped)
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

    _stub_missing_queries(model)

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
        elif re.fullmatch(r"\d{1,2}-\d{1,2}-\d{4}", inp.default or ""):
            # the platform TEXT-substituted whatever string sat here; PRD
            # binds a real date, so a backwards default must be repaired.
            # Day/month order: unambiguous when one part exceeds 12,
            # dd-mm-yyyy assumed (and said) otherwise.
            first, second, year = (int(v) for v in inp.default.split("-"))
            day, month, order = first, second, "dd-mm-yyyy"
            if first <= 12 < second:
                day, month, order = second, first, "mm-dd-yyyy"
            if 1 <= month <= 12 and 1 <= day <= 31:
                prm.default = f"{year}-{month:02d}-{day:02d} 00:00:00"
                model.issues.append(
                    f"parameter '{inp.name}' default {inp.default!r} is "
                    f"not ISO - repaired to '{prm.default}' (read as "
                    f"{order}; the original's own defect - the old "
                    "platform pasted the string into the SQL, PRD binds "
                    "a real date) - review the day/month order")
            else:
                model.issues.append(
                    f"parameter '{inp.name}' default {inp.default!r} is "
                    "not a valid date in any day/month order - the "
                    "database will reject it; fix the default to "
                    "yyyy-mm-dd hh:mm:ss")
        # A ${param} inside an IN (...) filter whose default is a comma list
        # is the platform's multi-select idiom: the prompt submitted several
        # values and the text substitution splatted them into the list. The
        # PRD-native equivalent is a MULTI-VALUE parameter - the engine
        # expands the selected array inside IN (${param}) - with the same
        # values pre-selected.
        if ("," in (inp.default or "")
                and re.search(r"\bIN\s*\(\s*\$\{%s\}\s*\)" % re.escape(inp.name),
                              model.sql or "", re.I)):
            prm.multi_value = True
            prm.default_values = [v.strip() for v in inp.default.split(",")
                                  if v.strip()]
            model.issues.append(
                f"parameter '{inp.name}' feeds an IN (...) filter with a "
                "comma-list default - converted to a PRD multi-select "
                "parameter with those values pre-selected; the engine "
                "expands the selection into the IN clause")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
                        prm.default or ""):
            prm.value_type = "DateField"

        # a no-default parameter filtering a column by EQUALITY gets a
        # query-backed dropdown over that very column (SELECT DISTINCT via
        # the folded-prompt machinery) and, having no default of its own,
        # the first available value - so the report opens WITH data
        # instead of an empty prompt
        if (not prm.default and not prm.default_values
                and inp.name not in model.param_lov_sql):
            eq = re.search(r"([A-Za-z_][\w.]*)\s*=\s*\$\{%s\}"
                           % re.escape(inp.name), model.sql or "")
            if eq:
                column = eq.group(1)
                model.param_sql_columns[inp.name] = column
                model.issues.append(
                    f"parameter '{inp.name}' had no default - converted to "
                    f"a query-backed dropdown over {column}; the platform "
                    "prompted for it every run")

        src = lookup_by_output.get(list_source)
        list_input = next((i for i in x.inputs
                           if i.name == list_source and i.list_maps), None)
        if src is not None and src.component == "SQLLookupRule":
            q = _PREPARE.sub(r"${}", src.deftext("query"))
            model.param_lov_sql[inp.name] = (q, vcol or "1", dcol or vcol
                                             or "1")
            model.issues.append(
                f"parameter '{inp.name}' pick-list converted as a "
                "query-backed PRD list parameter - its lookup rides along "
                f"as query 'lov_{inp.name}' (display {dcol!r}, "
                f"value {vcol!r})")
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
    _resolve_templated_bindings(model, x, derived)

    # ---- orchestration components -> suggested solutions -----------------
    def _clip(value, limit=40):
        text = " ".join(str(value).split())
        return text if len(text) <= limit else text[:limit] + "..."

    for a, got, stopped in script_states:
        script = a.deftext("script") or ""
        if got:
            model.issues.append(
                "JavaScript-derived value(s) evaluated at conversion time "
                "(the interpreter ran the same statements the platform "
                "ran): "
                + ", ".join(f"{n} = {_clip(v)!r}"
                            for n, v in sorted(got.items())[:6])
                + (", ..." if len(got) > 6 else "")
                + " - the query, bindings and labels use the computed "
                "values")
        remaining = [n for n, _t, _m in a.outputs if n not in got]
        if stopped is None or not remaining:
            continue
        # the rest of the script is outside the deterministic subset -
        # say WHICH platform idiom it is and the PRD-native replacement
        if "getValueAt" in script or "getRowCount" in script:
            model.issues.append(
                "JavaScript reads a prior lookup's result set into "
                f"value(s) {', '.join(remaining[:5])} - PRD-native: fold "
                "that lookup into the main query (a join or scalar "
                "subquery), or make each value a query-backed parameter "
                f"default. Evaluation stopped at: {_clip(stopped, 60)}")
        elif "Date(" in script:
            model.issues.append(
                "JavaScript computes report-run date part(s) "
                f"{', '.join(remaining[:5])} - PRD prints these itself: "
                "$(report.date, date, <pattern>) in a message field, or "
                "a =TODAY()-based expression; no parameter needed. "
                f"Evaluation stopped at: {_clip(stopped, 60)}")
        elif "JavaScriptResultSet" in script:
            model.issues.append(
                "JavaScript BUILDS a result set in code - recreate the "
                "rows as a SQL query or a PRD table datasource. "
                f"Evaluation stopped at: {_clip(stopped, 60)}")
        else:
            model.issues.append(
                "JavaScript business logic in the action sequence - fold "
                "it into the SQL as a computed column, or a PRD function/"
                f"formula. Script head: {_clip(script, 140)}")

    for a in x.actions:
        if a.component == "EmailComponent":
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

    # The same layout auto-fit/QA pass every Crystal model gets: nudges
    # always-visible overlaps apart and notes what it did. Layered
    # (visibility-conditioned) stacks are exempt - they render one per row -
    # and the lint's layered findings are folded into the notes so the
    # wireframe's stacked look is explained where the reviewer reads.
    from pentaho_migration.reports.layout_qa import autofit_layout, lint_layout
    autofit_layout(model)
    for f in lint_layout(model).findings:
        if f.code == "layered":
            model.issues.append(f"{f.band}: {f.message}")

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

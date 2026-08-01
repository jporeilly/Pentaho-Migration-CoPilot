"""The ETL review agent: SHIP or REVIEW for one converted mapping - with
evidence, exactly like the Crystal release gate.

For a report the deterministic check is a rendered comparison; for a
transformation it is the CONVERTED GRAPH itself plus, when available,
ground truth from a real PDI install and a measured CSV diff:

  * unmapped steps        - logic that does not exist in the output;
  * untranslated / review expressions - the script work outstanding;
  * hop integrity         - dangling endpoints, unreachable steps,
                            disconnected islands;
  * sorted-input hazards  - Group By / Merge Join with no Sort rows
                            upstream produce SILENTLY WRONG results;
  * placeholder connections - DB steps whose connection is environment-
                            specific by design (sandbox config, not a
                            defect);
  * a Pan run             - optional; a .ktr that loads and runs under
                            the real engine is ground truth;
  * a CSV parity result   - optional; folded in when the diff harness
                            has measured outputs.

Every check is deterministic; the LLM only ever ANNOTATES findings with
a resolution-or-guidance note, it never decides the verdict.
"""

from pydantic import BaseModel, Field

from pentaho_migration.ir import Pipeline

# PDI step types whose semantics REQUIRE sorted input; feeding them an
# unsorted stream is the classic silently-wrong-results migration defect.
SORT_REQUIRED = {"GroupBy": "Group By", "MergeJoin": "Merge Join",
                 "Unique": "Unique rows"}
SORTERS = {"SortRows"}
# steps that legitimately start or end a stream
SOURCE_TYPES = {"TableInput", "CsvInput", "TextFileInput", "ExcelInput",
                "GetSystemInfo", "RowGenerator", "DataGrid"}
TARGET_TYPES = {"TableOutput", "TextFileOutput", "ExcelOutput", "Delete",
                "Update", "InsertUpdate", "SynchronizeAfterMerge"}


class EtlFinding(BaseModel):
    severity: str              # error | warning | info
    code: str                  # unmapped-steps | expressions | hops | ...
    message: str
    evidence: list = Field(default_factory=list)
    resolution: str = ""       # filled by the LLM annotator (or left empty)


class EtlReviewCheck(BaseModel):
    verdict: str = "REVIEW"    # SHIP | REVIEW
    pipeline: str = ""
    steps_checked: int = 0
    hops_checked: int = 0
    checks_run: list = Field(default_factory=list)
    findings: list[EtlFinding] = Field(default_factory=list)


def _suggestions(pipeline: Pipeline) -> dict:
    from pentaho_migration.mapper import RulesMapper

    try:
        return RulesMapper.for_pipeline(pipeline).suggestions
    except Exception:
        return {}


def _check_unmapped(pipeline: Pipeline, findings: list) -> None:
    """One finding per unmapped TYPE - a component that repeats is one
    kind of work with one approach, not N separate problems."""
    by_type: dict = {}
    for step in pipeline.steps:
        if step.pdi_type is None:
            by_type.setdefault(step.source_type, []).append(step.name)
    suggestions = _suggestions(pipeline) if by_type else {}
    for source_type, names in sorted(by_type.items()):
        approach = suggestions.get(
            source_type,
            "no rules mapping - inspect the component in the source tool "
            "and rebuild its behaviour with PDI steps")
        findings.append(EtlFinding(
            severity="error", code="unmapped-steps",
            message=(f"{len(names)} step(s) of type '{source_type}' have no "
                     "PDI mapping - this logic does not exist in the "
                     f"converted output. Suggested approach: {approach}"),
            evidence=names[:8]))


def _check_expressions(pipeline: Pipeline, findings: list) -> None:
    todo = [(s.name, e.field) for s in pipeline.steps
            for e in s.expressions if e.translated is None]
    if todo:
        findings.append(EtlFinding(
            severity="error", code="expressions",
            message=(f"{len(todo)} expression(s) are not translated - the "
                     "step runs without them. Translate (✨ one click "
                     "in the app) or port each by hand"),
            evidence=[f"{step}.{field}" for step, field in todo[:8]]))
    review = [(s.name, e.field) for s in pipeline.steps
              for e in s.expressions if e.translated is not None]
    if review:
        findings.append(EtlFinding(
            severity="warning", code="expressions-review",
            message=(f"{len(review)} translated expression(s) await "
                     "verification - NULL handling differs between the "
                     "source engine and JavaScript (the original is kept "
                     "as a comment beside each translation)"),
            evidence=[f"{step}.{field}" for step, field in review[:8]]))


def _check_hops(pipeline: Pipeline, findings: list) -> None:
    names = {s.name for s in pipeline.steps}
    dangling = [f"{h.from_step} -> {h.to_step}" for h in pipeline.hops
                if h.from_step not in names or h.to_step not in names]
    if dangling:
        findings.append(EtlFinding(
            severity="error", code="hops",
            message=(f"{len(dangling)} hop(s) reference a step that does "
                     "not exist - the stream is broken at these points"),
            evidence=dangling[:8]))
    if len(pipeline.steps) < 2:
        return
    linked = ({h.from_step for h in pipeline.hops}
              | {h.to_step for h in pipeline.hops})
    isolated = [s.name for s in pipeline.steps if s.name not in linked]
    if isolated:
        findings.append(EtlFinding(
            severity="warning", code="hops",
            message=(f"{len(isolated)} step(s) are wired to nothing - "
                     "either dead weight from the source tool or a stream "
                     "the conversion lost; delete or reconnect them"),
            evidence=isolated[:8]))


def _upstream_has_sorter(pipeline: Pipeline, step_name: str) -> bool:
    """Walk the incoming hops looking for a Sort rows step; passing
    through row-preserving steps is fine, but another reordering or
    aggregating step resets the guarantee."""
    seen = set()
    frontier = [h.from_step for h in pipeline.hops if h.to_step == step_name]
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        step = pipeline.step(name)
        if step is None:
            continue
        if step.pdi_type in SORTERS:
            return True
        if step.pdi_type in SORT_REQUIRED:      # its OWN sort problem
            continue
        frontier.extend(h.from_step for h in pipeline.hops
                        if h.to_step == name)
    return False


def _check_sorted_input(pipeline: Pipeline, findings: list) -> None:
    hazards = []
    for step in pipeline.steps:
        label = SORT_REQUIRED.get(step.pdi_type or "")
        if label and not _upstream_has_sorter(pipeline, step.name):
            hazards.append(f"{step.name} ({label})")
    if hazards:
        findings.append(EtlFinding(
            severity="error", code="sorted-input",
            message=(f"{len(hazards)} step(s) require SORTED input and "
                     "have no Sort rows upstream - they will run and "
                     "produce silently wrong results. Insert a Sort rows "
                     "step on the group/join keys immediately upstream"),
            evidence=hazards[:8]))


def _check_connections(pipeline: Pipeline, ktr: str | None,
                       findings: list) -> None:
    if not ktr or "<connection/>" not in ktr:
        return
    db_steps = [s.name for s in pipeline.steps
                if s.pdi_type in ("TableInput", "TableOutput", "StreamLookup",
                                  "DatabaseLookup", "Delete", "Update",
                                  "InsertUpdate", "ExecSQL")]
    findings.append(EtlFinding(
        severity="info", code="connections",
        message=("database connections are environment-specific "
                 "placeholders by design - open each database step in "
                 "Spoon and point it at the SANDBOX connection before the "
                 "first run (the sandbox kit's setup.md walks through it)"),
        evidence=db_steps[:8]))


def _check_pan_run(pipeline: Pipeline, ktr: str, findings: list,
                   checks_run: list) -> None:
    """Ground truth: does the .ktr load and run under the real engine?
    Only meaningful when every connection is configured - a placeholder
    connection fails at initialize BY DESIGN, which proves nothing."""
    import tempfile
    from pathlib import Path

    from pentaho_migration.pdi_runner import find_pdi_home, run_artifact

    if find_pdi_home() is None:
        return
    if "<connection/>" in ktr:
        findings.append(EtlFinding(
            severity="info", code="sandbox-run",
            message=("a Pan run was skipped: the transformation's database "
                     "connections are unconfigured placeholders, so it "
                     "cannot initialize yet - run it from Spoon once the "
                     "sandbox connection is set")))
        return
    checks_run.append("pan-run")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / f"{pipeline.name}.ktr"
        path.write_text(ktr, encoding="utf-8")
        try:
            result = run_artifact(path)
        except Exception as exc:
            findings.append(EtlFinding(
                severity="warning", code="sandbox-run",
                message=f"the Pan run could not start ({exc})"))
            return
    if result.ok:
        findings.append(EtlFinding(
            severity="info", code="sandbox-run",
            message="the converted .ktr LOADS AND RUNS under Pan - the "
                    "generated XML is engine-valid ground truth"))
    else:
        findings.append(EtlFinding(
            severity="error", code="sandbox-run",
            message=(f"Pan rejected the converted .ktr ({result.meaning}) "
                     "- the output does not load/run as generated"),
            evidence=result.log_tail.splitlines()[-6:]))


def _fold_in_diff(diff, findings: list, checks_run: list) -> None:
    """A measured CSV parity result outranks every static prediction."""
    if diff is None:
        return
    checks_run.append("csv-parity")
    sample_ev = [f"row {s.row} · {s.column}: expected {s.expected!r}, "
                 f"got {s.actual!r}" for s in diff.samples[:6]]
    if diff.parity >= 0.999 and diff.row_count_match:
        findings.append(EtlFinding(
            severity="info", code="parity",
            message=(f"measured output parity: {diff.matching_rows} of "
                     f"{diff.expected_rows} row(s) match the original's "
                     "output on the sandbox data")))
    elif diff.parity >= 0.95:
        findings.append(EtlFinding(
            severity="warning", code="parity",
            message=(f"measured output parity {diff.parity:.1%} - small "
                     "differences on the sandbox data; inspect the samples"),
            evidence=sample_ev))
    else:
        findings.append(EtlFinding(
            severity="error", code="parity",
            message=(f"measured output parity {diff.parity:.1%} - the "
                     "outputs differ materially on the sandbox data"),
            evidence=sample_ev))


def review_pipeline(pipeline: Pipeline, ktr: str | None = None,
                    run_sandbox: bool = False, diff=None) -> EtlReviewCheck:
    """Run every deterministic check that CAN run and return the verdict.
    `ktr` enables the connection check and (with `run_sandbox`) the Pan
    run; `diff` folds in a measured validator.diff.DiffReport."""
    findings: list[EtlFinding] = []
    checks_run = ["unmapped-steps", "expressions", "hops", "sorted-input"]
    _check_unmapped(pipeline, findings)
    _check_expressions(pipeline, findings)
    _check_hops(pipeline, findings)
    _check_sorted_input(pipeline, findings)
    if ktr:
        checks_run.append("connections")
        _check_connections(pipeline, ktr, findings)
        if run_sandbox:
            _check_pan_run(pipeline, ktr, findings, checks_run)
    _fold_in_diff(diff, findings, checks_run)

    severity_rank = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: severity_rank.get(f.severity, 3))
    verdict = ("REVIEW" if any(f.severity == "error" for f in findings)
               else "SHIP")
    return EtlReviewCheck(
        verdict=verdict, pipeline=pipeline.name,
        steps_checked=len(pipeline.steps), hops_checked=len(pipeline.hops),
        checks_run=checks_run, findings=findings)


def annotate_etl_findings(check: EtlReviewCheck, pipeline: Pipeline,
                          settings=None, max_findings: int = 8) -> int:
    """Ask the LLM for a resolution-or-guidance note per finding.
    Advisory only: the verdict is already decided deterministically.
    Returns how many findings were annotated; 0 (with no exception) when
    no provider is configured."""
    from pentaho_migration.llm.settings import load_settings
    from pentaho_migration.llm.translate import chat_json

    worth = [f for f in check.findings if f.severity != "info"]
    if not worth:
        return 0
    settings = settings or load_settings()
    schema = {"type": "object",
              "properties": {"resolution": {"type": "string"}},
              "required": ["resolution"]}
    tool = pipeline.source_tool.value
    steps = [f"{s.name} ({s.source_type} -> {s.pdi_type or 'UNMAPPED'})"
             for s in pipeline.steps][:25]
    context = f"Mapping: {pipeline.name} ({tool}). Steps: {steps}."
    done = 0
    for finding in worth[:max_findings]:
        prompt = (
            f"You are reviewing a {tool} to Pentaho Data Integration "
            "conversion. A deterministic check of the converted "
            "transformation produced this finding:\n\n"
            f"[{finding.severity}/{finding.code}] {finding.message}\n"
            f"Evidence: {finding.evidence[:6]}\n\n"
            f"{context}\n\n"
            "In 2-4 sentences: if this is mechanically fixable in the .ktr "
            "or in Spoon, say exactly what to change (step, setting, "
            "value). If it needs judgment, write the guidance a consultant "
            "needs to resolve it quickly. No preamble.")
        try:
            reply = chat_json(settings,
                              [{"role": "user", "content": prompt}], schema)
            finding.resolution = (reply.get("resolution") or "").strip()
            done += 1 if finding.resolution else 0
        except Exception:
            break                      # provider missing/down - stop quietly
    return done

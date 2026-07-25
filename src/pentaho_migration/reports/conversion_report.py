"""Generate the markdown conversion report that accompanies every .prpt output.

The report is the honest half of the tool: everything the converter could
not translate mechanically lands here as an explicit work item.
"""

STATUS_ICON = {"auto": "OK", "review": "REVIEW", "manual": "MANUAL"}


def build_conversion_report(model, source_path, output_path):
    lines = []
    add = lines.append

    n_auto = sum(1 for f in model.formulas.values() if f.status == "auto")
    n_review = sum(1 for f in model.formulas.values() if f.status == "review")
    n_manual = sum(1 for f in model.formulas.values() if f.status == "manual")
    n_elements = sum(len(s.elements) for s in model.sections)

    add(f"# Conversion Report: {model.name}")
    add("")
    add(f"- **Source:** `{source_path}`")
    add(f"- **Output:** `{output_path}`")
    add(f"- **Sections:** {len(model.sections)} | **Elements:** {n_elements} | "
        f"**Groups:** {len(model.groups)} | **Parameters:** {len(model.parameters)} | "
        f"**Summaries:** {len(model.summaries)}")
    add(f"- **Formulas:** {n_auto} auto, {n_review} need review, {n_manual} manual")
    add("")

    add("## Data source")
    add("")
    add(f"- JNDI connection: `{model.jndi}` — create/verify this connection on the "
        "Pentaho Server (or swap to a native JDBC datasource in PRD).")
    if model.sql_generated:
        add("- The report used linked tables, not a SQL command. A SELECT was "
            "generated from the columns the layout references — **verify joins and aliases**:")
    else:
        add("- SQL taken from the Crystal command object:")
    add("")
    add("```sql")
    add(model.sql)
    add("```")
    add("")
    if model.record_selection and model.record_selection_folded:
        add("### Record selection formula (folded automatically)")
        add("")
        add("Folded into the SQL WHERE clause - parameter prompts now filter "
            "the report. Verify the clause against the original:")
    elif model.record_selection:
        add("### Record selection formula (MANUAL)")
        add("")
        add("Crystal's record selection must be folded into the SQL WHERE clause "
            "or a PRD filter expression:")
        add("")
        add("```")
        add(model.record_selection)
        add("```")
        add("")

    if model.formulas:
        add("## Formulas")
        add("")
        add("| Formula | Status | Result / Notes |")
        add("|---|---|---|")
        for f in model.formulas.values():
            notes = "; ".join(f.notes)
            if f.rewrite_class:
                detail = (f"`{f.prd_target()}` — report function generated in "
                          f"the bundle (Data tab > Functions in PRD)"
                          + (f" — {notes}" if notes else ""))
            elif f.status == "manual":
                detail = notes or "requires manual conversion"
            elif f.source == "llm":
                detail = (f"`{f.translation}` — ✨ LLM-translated, confidence "
                          f"**{f.llm_confidence}**" + (f" — {notes}" if notes else ""))
            else:
                detail = f"`{f.translation}`" + (f" — {notes}" if notes else "")
            detail = detail.replace("|", "\\|").replace("\n", " ")
            add(f"| {{@{f.name}}} | {STATUS_ICON[f.status]} | {detail} |")
        add("")
        manual = [f for f in model.formulas.values() if f.status == "manual"]
        if manual:
            add("### Original text of manual formulas")
            add("")
            for f in manual:
                add(f"**{{@{f.name}}}**")
                add("```")
                add(f.text)
                add("```")
            add("")

    if model.summaries:
        add("## Summaries -> report functions")
        add("")
        add("| Crystal summary | PRD function | Field | Group |")
        add("|---|---|---|---|")
        for s in model.summaries:
            add(f"| {s.name} | `{s.expression_name}` ({s.operation}) | "
                f"{s.field_ref} | {s.group_field or '(grand total)'} |")
        add("")

    if model.parameters:
        add("## Parameters")
        add("")
        for p in model.parameters:
            add(f"- `{p.name}` ({p.value_type}) — prompt: \"{p.prompt or p.name}\". "
            "Converted as a textbox parameter; wire it into the query as `${" + p.name + "}`.")
        add("")

    from pentaho_migration.reports.model import is_todo_element

    todo = []
    for s in model.sections:
        for el in s.elements:
            if is_todo_element(el):
                todo.append(f"- `{s.area_kind}`: {el.kind} \"{el.text or el.name}\" "
                            "emitted as a red TODO placeholder label.")
            for note in el.notes:
                todo.append(f"- `{s.area_kind}`: {note}")
    for issue in model.issues:
        todo.append(f"- {issue}")
    if todo:
        add("## Remaining manual work")
        add("")
        lines.extend(todo)
        add("")

    add("---")
    add("*Generated by CR-PRPT-Migration. Open the .prpt in Pentaho Report "
        "Designer, fix the flagged items, then publish to the Pentaho Server.*")
    return "\n".join(lines)

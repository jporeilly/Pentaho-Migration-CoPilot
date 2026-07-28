"""The consultant's prioritised, costed list of actions for one migration.

Everything else in the pipeline reports FACTS - what converted, what did not,
how the two renders differ. Facts are not a plan: a consultant opening a
report with forty notes still has to work out what to do first, how long it
takes, and what happens if they skip it.

This turns those facts into ACTIONS, each with:

    priority  - P1 blocks release, P2 affects correctness or effort,
                P3 is cosmetic. Derived from evidence, never from a guess.
    where     - the bands, elements or formulas the work actually lands in.
    why       - what the customer sees if it is skipped.
    how       - the concrete PRD steps, named menu by named menu.
    hours     - from the same constants as the effort estimate, so the plan
                and the headline number can never disagree.

Ordering is deterministic. Two runs over the same report produce the same
plan in the same order - a consultant's estimate must not move because a
model felt differently today.
"""

from dataclasses import dataclass, field

from pentaho_migration.reports import effort as _effort
from pentaho_migration.reports.model import is_todo_element
from pentaho_migration.reports.todo_kinds import MANUAL, split_todos

P1, P2, P3 = 1, 2, 3

PRIORITY_LABEL = {
    P1: "P1 · blocks release",
    P2: "P2 · correctness",
    P3: "P3 · cosmetic",
}

# Hours per item, by action kind. Sourced from the effort model so the plan
# totals and the headline estimate stay in step.
_HOURS = {
    "findings-error": 0.5,          # reconcile a rendered-output difference
    "findings-warning": 0.25,
    "placeholder": _effort.COPILOT_TODO,
    "formula-manual": _effort.COPILOT_MANUAL_FORMULA,
    "formula-review": _effort.COPILOT_REVIEW_FORMULA,
    "suppression": 0.2,
    "summary": 0.25,
    "group-sort": 0.3,
    "unresolved": 0.2,
    "datasource": 0.2,
    "parameters": _effort.COPILOT_PARAM,
    "cosmetic": 0.05,
    "drill-down": 0.05,
    "other": 0.1,
}


@dataclass
class Action:
    priority: int
    kind: str
    title: str
    why: str
    how: str
    count: int = 1
    hours: float = 0.0
    where: list = field(default_factory=list)   # names/locations
    items: list = field(default_factory=list)   # the underlying notes

    @property
    def label(self) -> str:
        return PRIORITY_LABEL[self.priority]


def _hours(kind: str, count: int) -> float:
    """Cost of N items of one kind. The first costs full price; the rest are
    discounted, because the second conditional-format fix in the same report
    is not the same job as the first."""
    per = _HOURS.get(kind, _HOURS["other"])
    if count <= 1:
        return round(per * count, 2)
    return round(per + per * 0.6 * (count - 1), 2)


def _element_locations(model, predicate, cap=8):
    out = []
    for section in model.sections:
        for el in section.elements:
            if predicate(el):
                out.append(f"{section.area_kind}/{el.name or el.kind}")
    return out[:cap]


def build_action_plan(model, check=None) -> list:
    """The ordered plan. Highest priority first, and within a priority the
    heaviest item first - a consultant reads top-down and stops when the
    budget runs out, so the order has to carry the meaning."""
    notes = list(model.issues)
    for section in model.sections:
        for el in section.elements:
            notes.extend(el.notes)
    manual = split_todos(notes)[MANUAL]

    actions = []

    # ---- P1: the rendered output does not match the original ----------
    if check is not None and getattr(check, "findings", None):
        errors = [f for f in check.findings if f.severity == "error"]
        warnings = [f for f in check.findings if f.severity == "warning"]
        if errors:
            actions.append(Action(
                P1, "findings-error",
                "Reconcile the rendered output against the original",
                "The release gate rendered both reports and found differences "
                "the customer would see on the page - missing values, dropped "
                "lines or content that moved. Until these are closed the "
                "conversion is not equivalent to the Crystal original.",
                "Open the .prpt in Report Designer and preview it beside the "
                "original in the Crystal viewer (the app's View original "
                "button opens both). Work the evidence lines below one at a "
                "time; each names the exact value or line that differs.",
                count=len(errors), hours=_hours("findings-error", len(errors)),
                where=[f.code for f in errors],
                items=[f"{f.message}" for f in errors]))
        if warnings:
            actions.append(Action(
                P2, "findings-warning",
                "Review the flagged layout differences",
                "Content that reflowed or pages that filled differently. Not "
                "wrong data, but the customer notices a total that slipped "
                "onto its own page.",
                "In Report Designer, check band heights and the Keep Together "
                "flag on the groups named below (right-click the group band > "
                "Attributes).",
                count=len(warnings),
                hours=_hours("findings-warning", len(warnings)),
                where=[f.code for f in warnings],
                items=[f.message for f in warnings]))

    # ---- P1: elements that could not be converted at all ---------------
    placeholders = _element_locations(model, is_todo_element)
    n_placeholders = sum(1 for s in model.sections for el in s.elements
                         if is_todo_element(el))
    if n_placeholders:
        actions.append(Action(
            P1, "placeholder",
            "Rebuild the elements that converted as placeholders",
            "These print as a visible TODO box instead of the sub-report, "
            "image or object Crystal had. They are the first thing a customer "
            "spots.",
            "Each placeholder carries the reason it could not convert. In "
            "Report Designer, delete the box and add the real element: "
            "sub-reports via Insert > Sub-Report, images via Insert > Image "
            "(the carved originals are in the bundle).",
            count=n_placeholders, hours=_hours("placeholder", n_placeholders),
            where=placeholders,
            items=[n for n in manual if "placeholder" in n.lower()]))

    # ---- P1: formulas the translator refused to guess at ---------------
    manual_formulas = [f for f in model.formulas.values()
                       if f.status == "manual"]
    if manual_formulas:
        actions.append(Action(
            P1, "formula-manual",
            "Rebuild the formulas that could not be translated",
            "The translator refuses to guess: rather than emit a formula that "
            "looks right and computes something else, it stops. Any field "
            "bound to one of these shows no value until it is rebuilt.",
            "Report Designer > Data tab > Functions. The conversion report "
            "lists the original Crystal text beside the reason it was "
            "refused - usually a shared variable carrying state between "
            "sections, which PRD expresses as a report function instead.",
            count=len(manual_formulas),
            hours=_hours("formula-manual", len(manual_formulas)),
            where=[f.name for f in manual_formulas][:8],
            items=[f"{f.name}: {'; '.join(f.notes)[:160]}"
                   for f in manual_formulas]))

    unresolved = [n for n in manual if "unresolved" in n.lower()
                  or "field reference is empty" in n.lower()]
    if unresolved:
        actions.append(Action(
            P1, "unresolved",
            "Bind the fields whose source could not be resolved",
            "The element exists but points at nothing, so it prints blank.",
            "Select the element in Report Designer and drag the right column "
            "onto it from the Data tab. The dump did not name a source, so "
            "the original .rpt in Crystal Designer is the reference.",
            count=len(unresolved), hours=_hours("unresolved", len(unresolved)),
            items=unresolved))

    # ---- P2: things that convert, but not faithfully -------------------
    suppression = [n for n in manual if "EnableSuppress" in n]
    if suppression:
        actions.append(Action(
            P2, "suppression",
            "Recreate the conditional suppression PRD could not express",
            "Crystal hides these sections on a condition that depends on "
            "state carried between sections. Left alone the section always "
            "prints - extra rows the original does not show.",
            "Select the band in Report Designer, open Attributes > "
            "style-expression > visible, and write the condition as a PRD "
            "formula. Where Crystal used a shared variable, the equivalent is "
            "usually a report function declared on the Data tab.",
            count=len(suppression), hours=_hours("suppression", len(suppression)),
            items=suppression))

    summaries = [n for n in manual if n.lower().startswith("summary ")]
    if summaries:
        actions.append(Action(
            P2, "summary",
            "Rebuild the summaries with no PRD equivalent",
            "A total that prints the wrong number is worse than one that is "
            "missing, because nobody checks it.",
            "Data tab > Functions. For percentages and ranked summaries the "
            "usual answer is to compute the value in the report query "
            "instead, then bind the field directly.",
            count=len(summaries), hours=_hours("summary", len(summaries)),
            items=summaries))

    group_sort = [n for n in manual if n.lower().startswith("group sort ")]
    if group_sort:
        actions.append(Action(
            P2, "group-sort",
            "Re-apply the group ordering and Top-N selection",
            "Crystal's Group Sort Expert can order groups by a total and keep "
            "only the top few, rolling the rest into Others. PRD has no "
            "equivalent, so every group prints, in query order - a Top 5 "
            "report becomes a full listing.",
            "Do it in the query: ORDER BY the aggregate, and use a windowed "
            "rank (or a UNION for the Others row) to keep the top N. The "
            "report itself then needs no change.",
            count=len(group_sort), hours=_hours("group-sort", len(group_sort)),
            items=group_sort))

    # ---- P2: always-present wiring steps -------------------------------
    embedded = len(getattr(getattr(model, "saved_rows", None), "rows", []) or [])
    if embedded:
        why = (f"The bundle carries {embedded:,} rows recovered from the .rpt "
               "so it opens and renders with no database. That is a preview "
               "dataset, not a live feed.")
        how = ("When the customer is ready for live data, Data tab > swap the "
               "inline table for the JNDI datasource already defined in the "
               f"bundle ({model.jndi or 'name it here'}), then verify the "
               "generated SELECT - joins and aliases especially.")
    else:
        why = ("The report reads through a JNDI connection that has to exist "
               "on the Pentaho Server under exactly this name, or it fails at "
               "publish time.")
        how = (f"Create the JNDI connection {model.jndi or '(unnamed)'} on the "
               "server (or switch the report to a native JDBC datasource in "
               "Report Designer), then run the generated SELECT once by hand "
               "to confirm the joins and aliases.")
    actions.append(Action(
        P2, "datasource", "Wire up the data source", why, how,
        count=1, hours=_hours("datasource", 1),
        where=[model.jndi or "(no JNDI name)"]))

    review_formulas = [f for f in model.formulas.values()
                       if f.status == "review"]
    if review_formulas:
        actions.append(Action(
            P2, "formula-review",
            "Glance over the formulas that translated with a caveat",
            "These produce a value; the question is whether it is the value "
            "Crystal produced. Scope and rounding are the usual differences.",
            "Compare each against the Crystal original - the conversion "
            "report prints them side by side.",
            count=len(review_formulas),
            hours=_hours("formula-review", len(review_formulas)),
            where=[f.name for f in review_formulas][:8],
            items=[f"{f.name}: {'; '.join(f.notes)[:160]}"
                   for f in review_formulas]))

    # ---- P3: cosmetic -------------------------------------------------
    cosmetic = [n for n in manual
                if "conditional" in n.lower() and "EnableSuppress" not in n]
    if cosmetic:
        actions.append(Action(
            P3, "cosmetic",
            "Apply the cosmetic conditional formatting",
            "Colour, position and style conditions. The report is correct "
            "without them; it just looks plainer than the original.",
            "Select the element, then Attributes > style-expression and pick "
            "the matching key (paint, background-color, font-bold). Only "
            "worth doing where the customer will notice.",
            count=len(cosmetic), hours=_hours("cosmetic", len(cosmetic)),
            items=cosmetic))

    drill = [n for n in manual if "drill-down" in n.lower()]
    if drill:
        actions.append(Action(
            P3, "drill-down",
            "Decide what to do with the drill-down-only bands",
            "Crystal hid these until the user drilled in. PRD has no "
            "drill-down, so they stay hidden - harmless, but they clutter the "
            "design view.",
            "Delete them in Report Designer if the top-level view is all the "
            "customer needs, or split them into a second report reached by a "
            "drill-through link.",
            count=len(drill), hours=_hours("drill-down", len(drill)),
            items=drill))

    claimed = set()
    for action in actions:
        claimed.update(action.items)
    leftovers = [n for n in manual if n not in claimed]
    if leftovers:
        actions.append(Action(
            P3, "other", "Work through the remaining notes",
            "Items that need a judgement call but do not fall into a group.",
            "Each note names what the pipeline found and why it stopped.",
            count=len(leftovers), hours=_hours("other", len(leftovers)),
            items=leftovers))

    actions.sort(key=lambda a: (a.priority, -a.hours, a.title))
    return actions


def plan_totals(actions) -> dict:
    """{priority: (item count, hours)} plus a 'total' key - the roll-up the
    report leads with."""
    out = {}
    for action in actions:
        n, h = out.get(action.priority, (0, 0.0))
        out[action.priority] = (n + action.count, round(h + action.hours, 2))
    out["total"] = (sum(n for n, _ in out.values()),
                    round(sum(h for _, h in out.values()), 2))
    return out

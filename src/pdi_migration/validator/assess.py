"""Pre-migration source assessment: turn export facts + mapped pipelines into
plain-language warnings the user reads BEFORE trusting a conversion.

Every rule here was motivated by something observed in the real-export corpus
(samples/informatica) — keep it that way: no speculative warnings.
"""

from collections import Counter

from pdi_migration.ir import Pipeline, SourceInfo, SourceWarning, WarningLevel


def assess_source(source: SourceInfo, pipelines: list[Pipeline]) -> SourceInfo:
    """Attach warnings to the SourceInfo (returns the same object, mutated)."""
    warn = source.warnings.append

    # -- structural scope ----------------------------------------------------
    if source.mappings == 0:
        warn(SourceWarning(
            level=WarningLevel.SERIOUS,
            text="This export contains no mappings — it is workflow/session-only "
                 "(exported without 'related objects'). There is nothing to convert; "
                 "re-export the folder including mappings.",
        ))
    if source.workflows or source.sessions:
        warn(SourceWarning(
            level=WarningLevel.WARNING,
            text=f"Contains {source.workflows} workflow(s) and {source.sessions} session(s). "
                 "Orchestration — scheduling, dependencies, error handling, session overrides — "
                 "is not converted in Phase 0 and must be rebuilt as PDI Jobs (.kjb) manually.",
        ))
    if source.mapplets:
        warn(SourceWarning(
            level=WarningLevel.WARNING,
            text=f"Contains {source.mapplets} mapplet(s). Mapplets are not expanded inline; "
                 "convert each mapplet separately and re-link the results.",
        ))

    # -- version-specific ----------------------------------------------------
    if source.product_version is None and source.repository_version:
        warn(SourceWarning(
            level=WarningLevel.WARNING,
            text=f"Unrecognized repository version {source.repository_version} — this export "
                 "format has not been tested against the corpus; review results closely.",
        ))
    elif source.product_version and source.product_version.startswith(("8", "9")):
        warn(SourceWarning(
            level=WarningLevel.INFO,
            text=f"Export from PowerCenter {source.product_version} "
                 f"(repository {source.repository_version}). Older releases differ in "
                 "expression-language behavior and session metadata; validation against "
                 "sample data is especially important.",
        ))

    # -- per-step findings across all mappings in the file --------------------
    unmapped = Counter(
        step.source_type
        for p in pipelines for step in p.steps
        if step.pdi_type is None
    )
    if unmapped:
        detail = ", ".join(f"{t} ×{n}" for t, n in unmapped.most_common())
        warn(SourceWarning(
            level=WarningLevel.SERIOUS,
            text=f"{sum(unmapped.values())} step(s) have no PDI mapping and require manual "
                 f"conversion: {detail}.",
        ))

    sql_overrides = sum(
        1 for p in pipelines for step in p.steps
        if step.source_type == "Source Qualifier" and step.properties.get("Sql Query")
    )
    if sql_overrides:
        warn(SourceWarning(
            level=WarningLevel.WARNING,
            text=f"{sql_overrides} Source Qualifier(s) carry SQL overrides. The SQL is copied "
                 f"verbatim into Table Input — review for "
                 f"{source.database_type or 'source-database'} dialect differences.",
        ))

    expressions = sum(
        1 for p in pipelines for s in p.steps for e in s.expressions
        if e.translated is None
    )
    if expressions:
        warn(SourceWarning(
            level=WarningLevel.INFO,
            text=f"{expressions} port expression(s) need translation from the Informatica "
                 "expression language; each is flagged as a TODO in its generated step.",
        ))

    if source.codepage and source.codepage.upper() not in ("UTF-8", "US-ASCII"):
        warn(SourceWarning(
            level=WarningLevel.INFO,
            text=f"Repository codepage is {source.codepage}; verify string comparisons and "
                 "sort orders behave identically in PDI.",
        ))

    return source

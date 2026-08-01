# Version

**1.44.0** - 2026-08-01

**The corpus2 gap list is closed.** 1.43.0 proved both old Pentaho report
dialects translate; this release took a 126-report harvest (breadboard,
lanit, pentaho-platform-5.0-OLD — 25x the original corpus) and worked its
ranked gap list to zero: **0 crashes, 0 unmapped function classes, 0
unmapped element templates, 125 of 126 reports with layouts** (the one
remainder ships its definition in a jar the estate never committed; the
extraction path is tested and works the moment the jar uploads).

**Report functions port on jar-verified evidence.** One shared translation
table serves both dialects: the old classes moved wholesale from
`org.jfree.report.*` to the PRD engine's packages — visibility switches,
element colouring, hyperlinks, BeanShell scripts (PRD still ships the same
interpreter) — and every ported class name is verified present in the local
engine jars by the test suite. Aggregate functions become summaries,
PageOfPages becomes the writer's own page function. The sequences'
JavaScript runs through a safe interpreter with prefix semantics: statements
evaluate in order and conversion stops honestly at the first construct
outside the subset, keeping everything the platform itself would have
computed. What remains manual is *pointed* — each note names the PRD-native
fix (fold the lookup into the query, `$(report.date)` for run-date parts).

**Every chart family the old platform authored now translates.** Category
charts (bar, line, area, pie) were already in; this release adds the XY
family — XY line, scatter, bubble, and time series — plus multi-pie, with
the emitter speaking the new collector API verified from the legacy-charts
jar's own metadata: the collectors dropped their `-Function` suffix, x/y/z
column properties introspect capitalised (`XValueColumn[0]` — the JavaBeans
two-capitals rule; the engine rejects the lowercase spelling), series named
by a data column use the indexed `seriesColumn[i]`, and the time period is
the Class-valued `timePeriod`. Authored properties the render depends on
ride along — `maxBubbleSize` above all, because the PRD default of zero
draws invisible bubbles. The chart scan lives in the shared functions
module, so the simple dialect translates `drawable-field` and chart
expressions through the same table the legacy-EXT parser uses. All five
shapes render through the real engine against SampleData rows.

**Hidden definitions resolve.** The resolution ladder climbs from explicit
action-resources through: a resource picked by name via a `resource-name`
input (the platform's own run-time selection, reproduced from its default);
the `report-definition*` convention; definitions extracted from uploaded
jars; definitions embedded inline in the xaction (the WAQR ad-hoc pattern,
parser-config properties substituted); a Report Designer 1.x `.report`
object tree standing in for a never-committed runtime XML — the third old
dialect, with its own parser; and a tolerant repair for a real estate defect
(a comment closed with `->>` instead of `-->` — the typo is fixed in place).

**Dead server images stop blocking review.** Image references resolve three
tiers deep: the old server's local webapps, then the solution folder by
basename, then a stamped same-size placeholder so layout review proceeds —
and estate triage aggregates every placeholder into one action: drop the
real file into the solution folder and every report that points at it fixes
at once.

**The demo experience was driven live and fixed live.** Reports open with
data on screen: query-backed pick-lists pre-select their first value from
the live connection, date parameters get real datepickers with repaired
defaults (`05-01-2005` becomes ISO, the day/month order stated), and the
schema assistant substitutes numeric defaults unquoted so HSQLDB accepts
the validation SQL. Source badges are drawn product marks (Crystal,
Informatica, Talend, Airflow, xaction), the consultant report renders for
every family, conversion reports render their collapsible sections, and
the launchers list all four migration families plus the PDI → Airflow
studio, the default Pentaho tool paths, and how to start the SampleData
HSQLDB.

Phase 1 remains complete — Informatica PowerCenter, SAP Crystal Reports,
Talend, and Pentaho Xactions (all three definition dialects).
See [CHANGELOG.md](CHANGELOG.md) for history.

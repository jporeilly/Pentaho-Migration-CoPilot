// Reports flow, step 1: structure + data source of the parsed Crystal report.
// Deterministic view — everything here came straight out of the RptToXml dump.

const BAND_TIPS = {
  ReportHeader: 'Printed once at the start of the report.',
  PageHeader: 'Repeated at the top of every page (lands in styles.xml in PRD).',
  GroupHeader: 'Printed at the start of each group value.',
  Detail: 'The item band — one row per record.',
  GroupFooter: 'Printed after each group — subtotals live here.',
  ReportFooter: 'Printed once at the end — grand totals live here.',
  PageFooter: 'Repeated at the bottom of every page (lands in styles.xml in PRD).',
}

export default function ReportsInspectPage({ summary }) {
  const c = summary.counts
  const tiles = [
    { value: c.sections, label: 'bands', tip: 'Report sections parsed from the dump.' },
    { value: c.elements, label: 'elements', tip: 'Labels, fields, lines, and boxes placed on the bands.' },
    { value: c.groups, label: 'groups', tip: 'Grouping levels — become PRD relational groups.' },
    { value: c.parameters, label: 'parameters', tip: 'Prompted values — become PRD parameters, referenced as ${name} in the query.' },
    { value: c.summaries, label: 'summaries', tip: 'Crystal summary fields — become PRD report functions (ItemSum, ItemCount, …).' },
  ]

  return (
    <>
      <h2 className="subhead">{summary.name}</h2>

      <div className="tiles">
        {tiles.map((t) => (
          <div className="tile" key={t.label} title={t.tip}>
            <div className="value">{t.value}</div>
            <div className="label">{t.label}</div>
          </div>
        ))}
      </div>

      <div className="report-grid">
        <div className="card">
          <header><h2>Report structure</h2></header>
          <table>
            <thead>
              <tr><th>Band</th><th>Group</th><th className="num">Elements</th><th className="num">Height</th></tr>
            </thead>
            <tbody>
              {summary.sections.map((s, i) => (
                <tr key={i}>
                  <td title={BAND_TIPS[s.area]}>{s.area}</td>
                  <td>{s.group === null ? '—' : `G${s.group + 1}`}</td>
                  <td className="num">{s.elements}</td>
                  <td className="num">{s.height}pt</td>
                </tr>
              ))}
            </tbody>
          </table>
          {summary.groups.length > 0 && (
            <p className="muted">Grouped by: {summary.groups.map((g) => <code key={g}>{g}</code>)}</p>
          )}
        </div>

        <div className="card">
          <header>
            <h2>Data source</h2>
            <span
              className={`badge ${summary.sql_generated ? 'review' : 'auto'}`}
              title={summary.sql_generated
                ? 'The report used linked tables, so this SELECT was generated from the columns the layout references. Verify joins and aliases.'
                : 'Taken verbatim from the Crystal SQL command object.'}
            >
              {summary.sql_generated ? '⚠ generated — verify joins' : '✓ from Crystal command'}
            </span>
          </header>
          <p className="muted">
            Wired to JNDI connection <code>{summary.jndi}</code> — create or verify it on the
            Pentaho Server, or swap to a native JDBC datasource in PRD.
          </p>
          <pre className="sql-pre">{summary.sql}</pre>
          {summary.record_selection && (
            <div className="source-warnings">
              <b>Record selection formula</b> — fold into the SQL WHERE clause or a PRD filter:
              <pre className="sql-pre">{summary.record_selection}</pre>
            </div>
          )}
        </div>
      </div>

      <div className="report-grid">
        <div className="card">
          <header><h2>Parameters</h2></header>
          {summary.parameters.length ? (
            <table>
              <thead><tr><th>Name</th><th>Type</th><th>Prompt</th><th>Default</th></tr></thead>
              <tbody>
                {summary.parameters.map((p) => (
                  <tr key={p.name}>
                    <td><code>{p.name}</code></td>
                    <td>{p.type}</td>
                    <td>{p.prompt || '—'}</td>
                    <td>{p.default || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="muted">None</p>}
        </div>

        <div className="card">
          <header><h2>Summaries → report functions</h2></header>
          {summary.summaries.length ? (
            <table>
              <thead><tr><th>Crystal summary</th><th>PRD function</th><th>Group</th></tr></thead>
              <tbody>
                {summary.summaries.map((s) => (
                  <tr key={s.expression}>
                    <td>{s.name}</td>
                    <td><code>{s.expression}</code> ({s.operation})</td>
                    <td>{s.group || 'grand total'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="muted">None</p>}
        </div>
      </div>
    </>
  )
}

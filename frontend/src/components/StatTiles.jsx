export default function StatTiles({ report }) {
  const pct = report.total_steps
    ? Math.round((report.auto / report.total_steps) * 100)
    : 0
  const tiles = [
    { value: report.total_steps, label: 'steps' },
    { value: <>{report.auto} <small>({pct}%)</small></>, label: '✓ auto-converted' },
    { value: report.review, label: '⚠ needs review' },
    { value: report.manual, label: '✋ manual handoff' },
    { value: report.untranslated_expressions, label: 'expressions to translate' },
  ]
  return (
    <div className="tiles">
      {tiles.map((t) => (
        <div className="tile" key={t.label}>
          <div className="value">{t.value}</div>
          <div className="label">{t.label}</div>
        </div>
      ))}
    </div>
  )
}

export default function StatTiles({ report }) {
  const pct = report.total_steps
    ? Math.round((report.auto / report.total_steps) * 100)
    : 0
  const tiles = [
    { value: report.total_steps, label: 'steps',
      tip: 'Total steps parsed from the mapping (transformations, sources, targets).' },
    { value: <>{report.auto} <small>({pct}%)</small></>, label: '✓ auto-converted',
      tip: 'Mapped 1:1 by the rules library with full config — no review expected.' },
    { value: report.review, label: '⚠ needs review',
      tip: 'Converted with assumptions or AI-translated expressions — a human should verify before use.' },
    { value: report.manual, label: '✋ manual handoff',
      tip: 'No safe PDI mapping exists — a human must convert these steps by hand.' },
    { value: report.untranslated_expressions, label: 'expressions to translate',
      tip: 'Informatica expressions not yet translated to PDI JavaScript (use ✨ Translate on the Map page).' },
  ]
  return (
    <div className="tiles">
      {tiles.map((t) => (
        <div className="tile" key={t.label} title={t.tip}>
          <div className="value">{t.value}</div>
          <div className="label">{t.label}</div>
        </div>
      ))}
    </div>
  )
}

import StatTiles from '../components/StatTiles.jsx'

export default function ValidatePage({ result }) {
  const { pipeline, report } = result
  const reviewItems = pipeline.steps.filter((s) => s.confidence !== 'auto')

  return (
    <section className="card">
      <header>
        <h2>Migration report <span>{pipeline.name}</span></h2>
      </header>
      <StatTiles report={report} />

      <h3 className="subhead">Human review checklist</h3>
      {reviewItems.length === 0 ? (
        <p className="hint-line">Every step auto-converted — nothing needs review. 🎉</p>
      ) : (
        <ol className="checklist">
          {reviewItems.map((s) => (
            <li key={s.name}>
              <span className={`badge ${s.confidence}`}>
                {s.confidence === 'review' ? '⚠' : '✋'} {s.confidence}
              </span>
              <div>
                <b>{s.name}</b> <span className="muted">({s.source_type} → {s.pdi_type ?? 'no mapping'})</span>
                <div className="notes">
                  {[...s.notes, ...s.expressions.map((e) => `Translate: ${e.field} = ${e.raw}`)].join('\n')}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}

      <div className="upcoming">
        <h3 className="subhead">Runtime diff harness — upcoming milestone</h3>
        <p className="hint-line">
          The next validation layer runs the original and converted pipelines against
          sample data and diffs the outputs row by row, scoring output parity per step.
          No conversion auto-deploys without passing it.
        </p>
      </div>
    </section>
  )
}

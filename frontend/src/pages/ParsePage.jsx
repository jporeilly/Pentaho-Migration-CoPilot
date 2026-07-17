import FlowDiagram from '../components/FlowDiagram.jsx'
import SourceCard from '../components/SourceCard.jsx'

export default function ParsePage({ result, source }) {
  const { pipeline } = result
  const expressions = pipeline.steps.reduce((n, s) => n + s.expressions.length, 0)

  return (
    <>
    {source && <SourceCard source={source} />}
    <section className="card">
      <header>
        <h2>Parsed structure <span>{pipeline.name}</span></h2>
        <p className="summary">
          <b>{pipeline.steps.length}</b> steps · <b>{pipeline.hops.length}</b> hops ·{' '}
          <b>{expressions}</b> expressions extracted
        </p>
      </header>
      <p className="hint-line">
        What the deterministic parser extracted from the export — structure only, nothing
        converted yet. Hover any diagram node or expand a step for its fields.
      </p>

      <FlowDiagram pipeline={pipeline} />

      <h3 className="subhead">Steps &amp; fields</h3>
      {pipeline.steps.map((s) => (
        <details className="step-detail" key={s.name}>
          <summary>
            <b>{s.name}</b>
            <span className="muted"> — {s.source_type} · {s.fields.length} fields
            {s.expressions.length > 0 && ` · ${s.expressions.length} expressions`}</span>
          </summary>
          {s.fields.length > 0 && (
            <table>
              <thead>
                <tr><th>Field</th><th>Type</th><th className="num">Precision</th><th>Expression</th></tr>
              </thead>
              <tbody>
                {s.fields.map((f) => {
                  const expr = s.expressions.find((e) => e.field === f.name)
                  return (
                    <tr key={f.name}>
                      <td>{f.name}</td>
                      <td>{f.datatype}</td>
                      <td className="num">{f.precision ?? '—'}</td>
                      <td className="notes">{expr ? expr.raw : ''}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </details>
      ))}
    </section>
    </>
  )
}

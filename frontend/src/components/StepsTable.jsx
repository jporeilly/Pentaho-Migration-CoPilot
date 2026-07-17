import { useState } from 'react'

const BADGES = { auto: '✓', review: '⚠', manual: '✋' }

export default function StepsTable({ steps }) {
  const [filter, setFilter] = useState('all')
  const counts = steps.reduce((acc, s) => {
    acc[s.confidence] = (acc[s.confidence] || 0) + 1
    return acc
  }, {})
  const visible = filter === 'all' ? steps : steps.filter((s) => s.confidence === filter)

  return (
    <>
      <div className="filters">
        <button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>
          All {steps.length}
        </button>
        {Object.entries(BADGES).map(([key, icon]) => (
          <button
            key={key}
            className={filter === key ? 'active' : ''}
            onClick={() => setFilter(key)}
          >
            {icon} {key} {counts[key] || 0}
          </button>
        ))}
      </div>

      <table>
        <thead>
          <tr>
            <th>Step</th><th>Source type</th><th>PDI type</th>
            <th>Confidence</th><th className="num">Fields</th><th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td>
              <td>{s.source_type}</td>
              <td>{s.pdi_type ?? '—'}</td>
              <td>
                <span className={`badge ${s.confidence}`}>
                  {BADGES[s.confidence]} {s.confidence}
                </span>
              </td>
              <td className="num">{s.fields.length}</td>
              <td className="notes">
                {[
                  ...s.notes,
                  ...s.expressions.map((e) =>
                    e.translated != null
                      ? `${e.field} = ${e.translated}${e.notes ? `  (${e.notes})` : ''}`
                      : `TODO ${e.field}: ${e.raw}`,
                  ),
                ].join('\n')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

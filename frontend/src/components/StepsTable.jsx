import { useState } from 'react'

const BADGES = { auto: '✓', review: '⚠', manual: '✋' }

const CONFIDENCE_TIPS = {
  auto: 'Mapped 1:1 by the rules library — no review expected.',
  review: 'Converted with assumptions or AI translation — verify before use.',
  manual: 'No safe PDI mapping — convert this step by hand.',
}

export const PDI_TIPS = {
  TableInput: 'Reads rows from a database via SQL.',
  TableOutput: 'Writes rows to a database table.',
  GroupBy: 'Aggregates rows — requires input sorted on the group keys.',
  SortRows: 'Sorts the row stream.',
  FilterRows: 'Routes rows by a true/false condition.',
  SwitchCase: 'Routes rows to targets by a field value.',
  MergeJoin: 'Joins two streams — both must be sorted on the join keys.',
  StreamLookup: 'Looks up values from a second stream held in memory.',
  Sequence: 'Adds a sequence counter to each row (resets per run unless DB-backed).',
  Append: 'Concatenates two streams (layouts must match).',
  InsertUpdate: 'Inserts new rows or updates existing ones by key.',
  Normaliser: 'Pivots repeating columns into rows.',
  ScriptValueMod: 'Runs JavaScript per row — translated expressions live here.',
  Dummy: 'Placeholder step — does nothing (used for unmapped types).',
}

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
              <td title={s.pdi_type ? PDI_TIPS[s.pdi_type] : 'No PDI mapping — manual conversion required.'}>
                {s.pdi_type ?? '—'}
              </td>
              <td>
                <span className={`badge ${s.confidence}`} title={CONFIDENCE_TIPS[s.confidence]}>
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

const LEVELS = {
  high:   { color: 'var(--status-serious)', icon: '✋' },
  medium: { color: 'var(--status-warning)', icon: '⚠' },
  low:    { color: 'var(--status-good)', icon: '✓' },
  none:   { color: 'var(--text-muted)', icon: '·' },
}

export default function ImpactPanel({ impact }) {
  const { summary, entries } = impact
  return (
    <div className="impact">
      <h3 className="subhead">
        Impact analysis — {summary.high} high · {summary.medium} medium · {summary.low} low · {summary.none} none
      </h3>

      {summary.top_risks.length > 0 && (
        <ul className="risk-list">
          {summary.top_risks.map((risk, i) => <li key={i}>⚠ {risk}</li>)}
        </ul>
      )}

      {entries.map((e) => {
        const level = LEVELS[e.impact] ?? LEVELS.none
        return (
          <details className="impact-entry" key={e.step}>
            <summary>
              <span className="impact-badge" style={{ color: level.color }}>
                {level.icon} {e.impact}
              </span>
              <b>{e.step}</b>
              <span className="muted"> — {e.source_type} → {e.pdi_type ?? 'no mapping'}</span>
            </summary>
            <div className="impact-body">
              <h4>What converts automatically</h4>
              <ul>{e.converts.map((c, i) => <li key={i}>{c}</li>)}</ul>
              {e.differences.length > 0 && (
                <>
                  <h4>Behavioral differences (Informatica → PDI)</h4>
                  <ul>{e.differences.map((d, i) => <li key={i}>{d}</li>)}</ul>
                </>
              )}
              {e.actions.length > 0 && (
                <>
                  <h4>Required actions</h4>
                  <ul>{e.actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
                </>
              )}
            </div>
          </details>
        )
      })}
    </div>
  )
}

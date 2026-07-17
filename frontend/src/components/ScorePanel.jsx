const GRADE_STATUS = {
  A: { color: 'var(--status-good)', icon: '✓' },
  B: { color: 'var(--status-good)', icon: '✓' },
  C: { color: 'var(--status-warning)', icon: '⚠' },
  D: { color: 'var(--status-serious)', icon: '⚠' },
  E: { color: 'var(--status-serious)', icon: '✋' },
}

export default function ScorePanel({ score }) {
  const status = GRADE_STATUS[score.grade] ?? GRADE_STATUS.C
  return (
    <div className="score-panel">
      <div className="score-hero">
        <div className="score-value" style={{ color: status.color }}>
          {score.score}
          <span className="score-max">/100</span>
        </div>
        <div className="score-meta">
          <span className="score-grade" style={{ color: status.color }}>
            {status.icon} Grade {score.grade}
          </span>
          <span className="score-kind">migration confidence · static prediction</span>
          <p className="score-verdict">{score.verdict}</p>
        </div>
      </div>
      <div className="score-factors">
        {score.factors.map((f) => (
          <div className="factor" key={f.name}>
            <div className="factor-head">
              <span>{f.name}</span>
              <b>{f.score}</b>
            </div>
            <span className="factor-detail">{f.detail}</span>
            <div className="factor-track">
              <div className="factor-bar" style={{ width: `${f.score}%` }} />
            </div>
          </div>
        ))}
      </div>
      <p className="score-note">
        Static score from mapping coverage, expression translation, config completeness, and
        semantic impact. Measured confidence (running old vs. new on data and diffing outputs)
        arrives with the diff-harness milestone.
      </p>
    </div>
  )
}

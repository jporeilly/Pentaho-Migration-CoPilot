import { useState } from 'react'

// Measured output parity: upload the original pipeline's CSV output and the
// converted pipeline's CSV output; the backend diffs them row by row.
export default function DiffRunner() {
  const [expected, setExpected] = useState(null)
  const [actual, setActual] = useState(null)
  const [key, setKey] = useState('')
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('expected', expected)
      form.append('actual', actual)
      const query = key ? `?key=${encodeURIComponent(key)}` : ''
      const res = await fetch(`/diff${query}`, { method: 'POST', body: form })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail || res.statusText)
      setReport(body)
    } catch (err) {
      setReport(null)
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const verdictClass = report?.verdict.startsWith('PASS')
    ? 'good' : report?.verdict.startsWith('NEAR') ? 'warn' : 'bad'

  return (
    <div className="diff-runner">
      <h3 className="subhead">Output parity check (measured)</h3>
      <p className="hint-line">
        Run the original mapping in Informatica and the converted .ktr in PDI — both
        against the sandbox data — export each output to CSV, and compare them here.
        This is the measured counterpart to the static confidence score.
      </p>
      <div className="diff-inputs">
        <label className="file-pick">
          Original output (CSV)
          <input type="file" accept=".csv" onChange={(e) => setExpected(e.target.files[0] ?? null)} />
        </label>
        <label className="file-pick">
          Converted output (CSV)
          <input type="file" accept=".csv" onChange={(e) => setActual(e.target.files[0] ?? null)} />
        </label>
        <label className="file-pick">
          Key column (optional)
          <input type="text" placeholder="e.g. CUSTOMER_ID" value={key} onChange={(e) => setKey(e.target.value)} />
        </label>
        <button className="primary" disabled={!expected || !actual || busy} onClick={run}>
          {busy ? 'Comparing…' : '⇄ Compare outputs'}
        </button>
      </div>
      {error && <div className="error">Comparison failed: {error}</div>}
      {report && (
        <div className="diff-report">
          <p className={`diff-verdict ${verdictClass}`}>
            {report.verdict} — parity {(report.parity * 100).toFixed(1)}%
          </p>
          <p className="summary">
            rows: {report.expected_rows} original / {report.actual_rows} converted ·
            matching {report.matching_rows} · mismatched {report.mismatched_rows}
            {report.missing_rows > 0 && ` · missing ${report.missing_rows}`}
            {report.extra_rows > 0 && ` · extra ${report.extra_rows}`}
          </p>
          {report.columns.length > 0 && (
            <p className="summary">
              columns with mismatches:{' '}
              {report.columns.map((c) => `${c.column} (${c.mismatches})`).join(', ')}
            </p>
          )}
          {report.samples.length > 0 && (
            <table>
              <thead>
                <tr><th>Row</th><th>Column</th><th>Original</th><th>Converted</th></tr>
              </thead>
              <tbody>
                {report.samples.map((s, i) => (
                  <tr key={i}>
                    <td>{s.row}</td><td>{s.column}</td>
                    <td className="notes">{s.expected}</td>
                    <td className="notes">{s.actual}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

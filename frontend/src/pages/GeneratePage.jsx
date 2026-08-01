// ETL flow, step 3: the generated .ktr, gated by the review agent -
// the ETL counterpart of the Crystal Download page. Run 🛡 Review first:
// deterministic checks over the converted graph (unmapped steps,
// expressions, hop integrity, sorted-input hazards, optionally a real
// Pan run), findings LLM-annotated, and the per-mapping consultant
// report - downloads unlock when it completes.

import { useState } from 'react'
import ReportOverlay from '../components/ReportOverlay.jsx'
import StageBar from '../components/StageBar.jsx'

function downloadPdf(base64, filename) {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }))
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

function downloadText(text, filename, type = 'application/xml') {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type }))
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

const SEV_ICON = { error: '✋', warning: '⚠', info: 'ℹ' }

export default function GeneratePage({ result }) {
  const { pipeline, ktr } = result
  const [busy, setBusy] = useState(false)
  const [stageState, setStageState] = useState(null)
  const [review, setReview] = useState(null)
  const [reviewError, setReviewError] = useState(null)
  const [runSandbox, setRunSandbox] = useState(false)
  const [overlayHtml, setOverlayHtml] = useState(null)

  async function runReview() {
    setBusy(true)
    setReview(null)
    setReviewError(null)
    try {
      const rate = Number(localStorage.getItem('consultantRate')) || 150
      const res = await fetch('/review/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pipeline, ktr, run_sandbox: runSandbox, rate }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail || res.statusText)
      for (;;) {
        await new Promise((r) => setTimeout(r, 1000))
        const s = await fetch(`/review/status?job=${body.job}`)
        const state = await s.json()
        if (!s.ok) throw new Error(state.detail || s.statusText)
        setStageState({ stage: state.stage, stages: state.stages })
        if (state.status === 'done') { setReview(state.result); break }
        if (state.status === 'error') throw new Error(state.detail || 'review failed')
      }
    } catch (err) {
      // the agent could not run - say so and UNLOCK the download rather
      // than deadlock the user (mirrors the Crystal release gate)
      setReviewError(err.message)
    } finally {
      setBusy(false)
      setStageState(null)
    }
  }

  const downloadsLocked = !review && !reviewError
  const lockHint = downloadsLocked
    ? 'Run the 🛡 Review agent first - the download unlocks when it completes'
    : undefined

  return (
    <>
      <section className="card">
        <header>
          <h2>Generated transformation <span>{pipeline.name}.ktr</span></h2>
          <div className="actions">
            <button className="primary" onClick={runReview} disabled={busy}
              title="Deterministic checks over the converted graph - unmapped steps, expressions, hop integrity, sorted-input hazards - plus the consultant report. Findings are LLM-annotated when a provider is configured.">
              {busy ? 'Reviewing…' : '🛡 Review agent'}
            </button>
            <label className="jndi-field" title="Also load-and-run the .ktr through a local PDI install (Pan) - skipped automatically when connections are unconfigured placeholders">
              <input type="checkbox" checked={runSandbox}
                onChange={(e) => setRunSandbox(e.target.checked)} />
              {' '}Pan run
            </label>
            <button className="ghost" disabled={downloadsLocked} title={lockHint}
              onClick={() => downloadText(ktr, `${pipeline.name}.ktr`)}>
              ⬇ Download .ktr
            </button>
          </div>
        </header>
        <p className="hint-line">
          Opens in Spoon as an editable transformation. Steps marked <em>review</em> or{' '}
          <em>manual</em> carry their notes and TODO expressions in the step description —
          nothing unconverted is hidden.
        </p>
        {reviewError && (
          <div className="error">
            Review could not run: {reviewError} — the download is unlocked.
          </div>
        )}
        {downloadsLocked && (
          <p className="muted">
            🛡 Run the <b>Review agent</b> to unlock the download — it checks the
            converted graph deterministically and produces the consultant report,
            so you hand over output that has already been reviewed.
          </p>
        )}
      </section>

      {stageState && (
        <div className="card">
          <header><h2>Review agent <span>checking the converted graph…</span></h2></header>
          <StageBar stage={stageState.stage} stages={stageState.stages} />
          <p className="muted">
            Lint checks are instant; a Pan run or LLM annotation takes longer.
          </p>
        </div>
      )}

      {review && (
        <div className="card">
          <header>
            <h2>
              Review{' '}
              <span className={review.verdict === 'SHIP' ? 'gate-ship' : 'gate-review'}>
                {review.verdict === 'SHIP' ? '✅ SHIP' : '⚠ REVIEW'}
              </span>
            </h2>
          </header>
          <p className="muted">
            {review.steps_checked} step(s) and {review.hops_checked} hop(s) through{' '}
            {review.checks_run.join(', ')}.
            {review.llm_annotated > 0 && ` ${review.llm_annotated} finding(s) annotated by the LLM.`}
          </p>
          {review.findings.length === 0 ? (
            <p className="muted">No findings — the converted graph is complete and wired.</p>
          ) : (
            <ul className="notes">
              {review.findings.map((f, i) => (
                <li key={i}>
                  <b>{SEV_ICON[f.severity] || 'ℹ'} [{f.code}]</b> {f.message}
                  {f.evidence?.length > 0 && (
                    <div className="muted">{f.evidence.slice(0, 6).join(' · ')}</div>
                  )}
                  {f.resolution && <div className="gate-resolution">→ {f.resolution}</div>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {review && (
        <div className="card">
          <header>
            <h2>Consultant report</h2>
            <div className="actions">
              {review.consultant_report_html && (
                <button className="primary"
                  onClick={() => setOverlayHtml(review.consultant_report_html)}>
                  🔍 View
                </button>
              )}
              {review.consultant_report_html && (
                <button className="ghost" onClick={() => downloadText(
                  review.consultant_report_html,
                  `${pipeline.name}.consultant.html`, 'text/html')}>
                  ⬇ .html
                </button>
              )}
              {review.consultant_report_pdf && (
                <button className="ghost" onClick={() => downloadPdf(
                  review.consultant_report_pdf,
                  `${pipeline.name}.consultant.pdf`)}>
                  ⬇ .pdf
                </button>
              )}
              {review.consultant_report_markdown && (
                <button className="ghost" onClick={() => downloadText(
                  review.consultant_report_markdown,
                  `${pipeline.name}.consultant.md`, 'text/markdown')}>
                  ⬇ .md
                </button>
              )}
            </div>
          </header>
          <p className="muted">Action plan + costed effort — produced by the
            review agent from the converted graph and its findings.</p>
        </div>
      )}

      <section className="card">
        <header><h2>Transformation XML</h2></header>
        <pre className="ktr-pre">{ktr}</pre>
      </section>

      {overlayHtml && (
        <ReportOverlay
          html={overlayHtml}
          title="Consultant report"
          filename={`${pipeline.name}.consultant.html`}
          onClose={() => setOverlayHtml(null)}
        />
      )}
    </>
  )
}

import React, { useCallback, useEffect, useState } from 'react'
import Explain from '../components/Explain.jsx'
import StageBar from '../components/StageBar.jsx'

const STATUSES = ['converted', 'in_review', 'verified', 'failed']
const STATUS_ICON = { converted: '·', in_review: '⚠', verified: '✓', failed: '✋' }

const TRIAGE_ICON = { READY: '✓', REVIEW: '⚠', BLOCKED: '✋' }

// Filter chips over the report table. "NONE" is the honest bucket for reports
// that have never been triaged — otherwise they hide inside "all" and a
// consultant thinks the sweep covered them.
const VERDICTS = [
  { key: 'all', label: 'All' },
  { key: 'READY', label: '✓ READY' },
  { key: 'REVIEW', label: '⚠ REVIEW' },
  { key: 'BLOCKED', label: '✋ BLOCKED' },
  { key: 'NONE', label: 'not triaged' },
]

export default function ProjectPage({ onBack, onOpen, context }) {
  const [rows, setRows] = useState(null)
  const [reports, setReports] = useState([])
  const [showAll, setShowAll] = useState(false)
  const [jndi, setJndi] = useState(localStorage.getItem('triageJndi') || '')
  const [triaging, setTriaging] = useState(false)
  const [etlReviewing, setEtlReviewing] = useState(false)
  const [sweep, setSweep] = useState(null)      // {kind, stage, stages, done, total, detail}
  const [expanded, setExpanded] = useState(null)     // report file with open detail
  const [parityBusy, setParityBusy] = useState(null) // report file being checked
  const [agentError, setAgentError] = useState('')
  // A real engagement lands 150 reports in here; without a filter the table is
  // a scroll, not a worklist.
  const [reportQuery, setReportQuery] = useState('')
  const [reportVerdict, setReportVerdict] = useState('all')
  const [estateBusy, setEstateBusy] = useState(false)
  const [estate, setEstate] = useState(null)     // {stage,stages,done,total,detail} while running
  const [estateResult, setEstateResult] = useState(null)
  const [packBusy, setPackBusy] = useState(false)
  const [pack, setPack] = useState(null)

  const refresh = useCallback(async () => {
    const res = await fetch('/project')
    if (res.ok) setRows(await res.json())
    const rep = await fetch('/project/reports')
    if (rep.ok) setReports(await rep.json())
  }, [])

  useEffect(() => { refresh() }, [refresh])

  async function updateStatus(row, status) {
    await fetch('/project/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file: row.file, mapping: row.mapping, status }),
    })
    refresh()
  }

  async function updateReportStatus(row, status) {
    await fetch('/project/report-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file: row.file, status }),
    })
    refresh()
  }

  async function pollEstate(job, setProgress) {
    for (;;) {
      await new Promise((r) => setTimeout(r, 800))
      const st = await fetch(`/project/estate/status?job=${job}`)
      const state = await st.json()
      if (!st.ok) throw new Error(state.detail || st.statusText)
      setProgress({ stage: state.stage, stages: state.stages,
                    done: state.done, total: state.total, detail: state.detail })
      if (state.status === 'done') return state.result
      if (state.status === 'error') throw new Error(state.detail || 'job failed')
    }
  }

  async function runEstateBatch(files) {
    if (!files?.length) return
    setEstateBusy(true)
    setEstateResult(null)
    setAgentError('')
    try {
      const form = new FormData()
      for (const f of files) form.append('exports', f)
      const res = await fetch(`/project/batch/start?jndi=${encodeURIComponent(jndi)}`,
                              { method: 'POST', body: form })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail || res.statusText)
      const result = await pollEstate(body.job, setEstate)
      setEstateResult(result)
      refresh()
    } catch (err) {
      setAgentError(`Batch convert failed: ${err.message}`)
    } finally {
      setEstateBusy(false)
      setEstate(null)
    }
  }

  async function runPack() {
    setPackBusy(true)
    setPack(null)
    setAgentError('')
    try {
      const rate = localStorage.getItem('consultantRate') || '150'
      const res = await fetch(
        `/project/pack/start?jndi=${encodeURIComponent(jndi)}&rate=${encodeURIComponent(rate)}`,
        { method: 'POST' })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail || res.statusText)
      setPack(await pollEstate(body.job, setEstate))
    } catch (err) {
      setAgentError(`Deliverable pack failed: ${err.message}`)
    } finally {
      setPackBusy(false)
      setEstate(null)
    }
  }

  async function pollSweep(job, kind) {
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000))
      const st = await fetch(`/project/sweep/status?job=${job}`)
      const state = await st.json()
      if (!st.ok) throw new Error(state.detail || st.statusText)
      setSweep({ kind, stage: state.stage, stages: state.stages,
                 done: state.done, total: state.total, detail: state.detail })
      if (state.status === 'done') return state.result
      if (state.status === 'error') throw new Error(state.detail || `${kind} failed`)
    }
  }

  async function runTriage() {
    setTriaging(true)
    setAgentError('')
    localStorage.setItem('triageJndi', jndi)
    try {
      const res = await fetch(`/project/reports/triage/start?jndi=${encodeURIComponent(jndi)}`,
                              { method: 'POST' })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail || res.statusText)
      setReports(await pollSweep(body.job, 'triage'))
    } catch (err) {
      setAgentError(`Triage failed: ${err.message}`)
    } finally {
      setTriaging(false)
      setSweep(null)
    }
  }

  async function runEtlReview() {
    setEtlReviewing(true)
    setAgentError('')
    try {
      const res = await fetch('/project/etl-review/start', { method: 'POST' })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail || res.statusText)
      setRows(await pollSweep(body.job, 'review'))
    } catch (err) {
      setAgentError(`Review sweep failed: ${err.message}`)
    } finally {
      setEtlReviewing(false)
      setSweep(null)
    }
  }

  async function runParity(row, file) {
    if (!file) return
    setParityBusy(row.file)
    setAgentError('')
    try {
      const body = new FormData()
      body.append('reference', file)
      const res = await fetch(
        `/project/report-parity?file=${encodeURIComponent(row.file)}&jndi=${encodeURIComponent(jndi)}`,
        { method: 'POST', body })
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText)
      refresh()
    } catch (err) {
      setAgentError(`Parity failed for ${row.name}: ${err.message}`)
    } finally {
      setParityBusy(null)
    }
  }

  function reviewSummary(row) {
    try {
      const d = JSON.parse(row.review_json || '{}')
      const parts = (d.findings || d.reasons || []).slice(0, 4)
      return parts.map((f) => (typeof f === 'string' ? f : `[${f.code}] ${f.message}`)).join('\n')
    } catch {
      return ''
    }
  }

  function gateSummary(row) {
    try {
      const d = JSON.parse(row.gate_json || '{}')
      const head = `original ${d.original_pages}pp vs converted ${d.converted_pages}pp`
      const finds = (d.findings || []).slice(0, 4).map((f) => `[${f.code}] ${f.message}`)
      return [head, ...finds].join('\n')
    } catch {
      return ''
    }
  }

  function triageDetail(row) {
    try {
      return JSON.parse(row.triage_json || '{}')
    } catch {
      return {}
    }
  }

  if (rows === null) return <p className="loading">Loading project…</p>

  if (!rows.length && !reports.length) {
    return (
      <>
      <button className="ghost back-btn" onClick={onBack}>← Back to workflow</button>
      <section className="card">
        <h2>Migration project</h2>
        <p className="hint-line">
          The project store is empty. Batch-convert a folder of exports first:
        </p>
        <pre className="ktr-pre">{'pentaho-migrate batch samples\\informatica\npentaho-migrate report-batch samples\\crystal\\real'}</pre>
        <p className="hint-line">
          Every mapping and report lands here with its metrics and a review status you
          can track through <em>converted → in review → verified</em>.
        </p>
      </section>
      </>
    )
  }

  // families: Talend jobs are .item exports, everything else ETL is Informatica
  const talendRows = rows.filter((r) => r.file.toLowerCase().endsWith('.item'))
  const infaRows = rows.filter((r) => !r.file.toLowerCase().endsWith('.item'))
  const families = [
    { key: 'informatica', label: 'Informatica pipelines', list: infaRows },
    { key: 'talend', label: 'Talend jobs', list: talendRows },
  ].filter((f) => f.list.length > 0)
  const visible = (key) => showAll || !context || context === key

  const reportNeedle = reportQuery.trim().toLowerCase()
  const shownReports = reports.filter((r) => {
    if (reportVerdict !== 'all'
        && (r.triage_verdict || 'NONE') !== reportVerdict) return false
    if (!reportNeedle) return true
    return `${r.name} ${r.file}`.toLowerCase().includes(reportNeedle)
  })
  const filtered = context && !showAll

  function familyStats(list) {
    const copilot = list.reduce((n, r) => n + (r.copilot_hours || 0), 0)
    const manual = list.reduce((n, r) => n + (r.manual_hours || 0), 0)
    const rate = Number(localStorage.getItem('consultantRate') || '150')
    return {
      copilot: Math.round(copilot), manual: Math.round(manual),
      saved: Math.round(manual - copilot),
      pct: manual > 0 ? Math.round(((manual - copilot) / manual) * 100) : 0,
      dollars: Math.round((manual - copilot) * rate).toLocaleString(),
    }
  }

  function StatsStrip({ list, scored }) {
    const s = familyStats(list)
    const avgScore = scored && list.length
      ? Math.round(list.reduce((n, r) => n + r.score, 0) / list.length) : null
    if (s.manual <= 0) return null
    return (
      <p className="family-stats">
        {avgScore !== null && <>avg confidence <b>{avgScore}/100</b> · </>}
        ~<b>{s.copilot}h</b> with Copilot vs ~<b>{s.manual}h</b> manual
        {' — saves '}<b>{s.saved}h</b> ({s.pct}%, ~${s.dollars})
      </p>
    )
  }

  function EtlFamilyCard({ family }) {
    const [q, setQ] = useState('')
    const [agent, setAgent] = useState('all')
    const needle = q.trim().toLowerCase()
    const shown = family.list.filter((r) => {
      if (agent !== 'all' && (r.review_verdict || 'NONE') !== agent) return false
      if (!needle) return true
      return `${r.mapping} ${r.file}`.toLowerCase().includes(needle)
    })
    return (
      <section className="card">
        <header>
          <h2>{family.label} <span>
            {shown.length === family.list.length
              ? `${family.list.length} converted`
              : `${shown.length} of ${family.list.length}`}
          </span></h2>
          <div className="triage-bar">
            <button className="primary" onClick={runEtlReview} disabled={etlReviewing}
              title="Run the ETL review agent over every stored mapping: unmapped steps, expressions, hop integrity, sorted-input hazards — verdicts persist in the store">
              {etlReviewing ? 'Reviewing…' : '🛡 Review sweep'}
            </button>
            <a
              className="ghost portfolio-link"
              href={`/project/portfolio?family=${family.key}&rate=${encodeURIComponent(localStorage.getItem('consultantRate') || '150')}`}
              target="_blank"
              rel="noreferrer"
              title="Self-contained HTML consultant report for this family: confidence grades, unmapped-component breakdown, review load, focus list, $ figures — prints to PDF"
            >
              📊 Consultant report
            </a>
          </div>
        </header>
        {sweep?.kind === 'review' && (
          <StageBar stage={sweep.stage} stages={sweep.stages}
            done={sweep.done} total={sweep.total} detail={sweep.detail} />
        )}
        <div className="filters report-filters">
          {[['all', 'all'], ['SHIP', '✅ SHIP'], ['REVIEW', '⚠ REVIEW'],
            ['NONE', 'not reviewed']].map(([key, label]) => {
            const n = key === 'all'
              ? family.list.length
              : family.list.filter((r) => (r.review_verdict || 'NONE') === key).length
            return (
              <button key={key} className={agent === key ? 'active' : ''}
                onClick={() => setAgent(key)} disabled={n === 0 && key !== 'all'}>
                {label} {n}
              </button>
            )
          })}
          <input className="jndi-input report-search"
            placeholder="Filter by mapping or export name…"
            value={q} onChange={(e) => setQ(e.target.value)} />
          {(q || agent !== 'all') && (
            <button onClick={() => { setQ(''); setAgent('all') }}>clear</button>
          )}
        </div>
        <StatsStrip list={shown} scored />
        <EtlTable list={shown} />
      </section>
    )
  }

  function EtlTable({ list }) {
    return (
      <div className="table-scroll">
        <table className="project-table">
          <thead>
            <tr>
              <th className="num">Score</th><th>Mapping</th><th>Export file</th>
              <th className="num">Steps</th><th className="num">Auto</th>
              <th className="num">Review</th><th className="num">Manual</th>
              <th className="num" title="Estimated hours saved vs a manual rebuild">Saved</th>
              <th title="The ETL review agent's verdict (deterministic checks over the converted graph)">Agent</th>
              <th>Status</th><th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r) => (
              <tr
                key={`${r.file}:${r.mapping}`}
                className="row-link"
                title="Open this mapping in the workflow"
                onClick={() => onOpen(r)}
              >
                <td className="num">
                  <span className={`score-chip grade-${r.grade}`}>{r.score} {r.grade}</span>
                </td>
                <td className="cell-clip mapping-link" title={r.mapping}>{r.mapping} →</td>
                <td className="notes cell-clip" title={r.file}>{r.file}</td>
                <td className="num">{r.steps}</td>
                <td className="num">{r.auto}</td>
                <td className="num">{r.review}</td>
                <td className="num">{r.manual}</td>
                <td className="num saved-cell">{r.saved_hours ? `${r.saved_hours}h` : '—'}</td>
                <td>
                  {r.review_verdict
                    ? <span className={r.review_verdict === 'SHIP' ? 'gate-ship' : 'gate-review'}
                        title={reviewSummary(r)}>
                        {r.review_verdict === 'SHIP' ? '✅ SHIP' : '⚠ REVIEW'}
                      </span>
                    : <span className="muted">—</span>}
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <select
                    className="status-select"
                    value={r.status}
                    onChange={(e) => updateStatus(r, e.target.value)}
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>{s.replace('_', ' ')}</option>
                    ))}
                  </select>
                </td>
                <td className="cell-time">{r.updated_at.slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <>
    <button className="ghost back-btn" onClick={onBack}>← Back to workflow</button>
    <section className="card">
      <header>
        <h2>
          Migration project{' '}
          <span>
            {infaRows.length ? `${infaRows.length} Informatica` : ''}
            {talendRows.length ? `${infaRows.length ? ' · ' : ''}${talendRows.length} Talend` : ''}
            {reports.length ? ` · ${reports.length} Crystal` : ''}
          </span>
        </h2>
        <div className="triage-bar">
          <label className={estateBusy ? 'ghost file-btn disabled' : 'ghost file-btn'}
            title="Batch-convert a selection of exports into the project store: PowerCenter/Talend XML, RptToXml dumps, .rpt binaries, .xactions, solution zips — routed by content">
            {estateBusy ? 'Converting…' : '⬆ Batch convert exports'}
            <input type="file" multiple hidden disabled={estateBusy}
              onChange={(e) => { runEstateBatch([...e.target.files]); e.target.value = '' }} />
          </label>
          <button className="primary" onClick={runPack} disabled={packBusy}
            title="One zip: every stored artifact re-converted, its consultant report beside it, the portfolio reports and a manifest — the engagement hand-over">
            {packBusy ? 'Packing…' : '📦 Deliverable pack'}
          </button>
          <a className="ghost portfolio-link" href="/project/export"
            title="Download the whole project store (sqlite) — move the engagement to another machine and import it there">
            ⬇ Export store
          </a>
          <label className="ghost file-btn"
            title="Replace this store with an exported one — the current store is backed up beside itself first">
            ⬆ Import store
            <input type="file" hidden accept=".db"
              onChange={async (e) => {
                const f = e.target.files[0]
                e.target.value = ''
                if (!f) return
                setAgentError('')
                const form = new FormData()
                form.append('store', f)
                const res = await fetch('/project/import', { method: 'POST', body: form })
                const body = await res.json().catch(() => ({}))
                if (!res.ok) { setAgentError(`Import failed: ${body.detail || res.statusText}`); return }
                refresh()
              }} />
          </label>
          <button className="ghost" onClick={refresh}>↻ Refresh</button>
        </div>
      </header>
      {estate && (
        <StageBar stage={estate.stage} stages={estate.stages}
          done={estate.done} total={estate.total} detail={estate.detail} />
      )}
      {estateResult && (
        <p className="summary">
          Batch converted <b>{estateResult.etl_mappings}</b> ETL mapping(s) and{' '}
          <b>{estateResult.reports}</b> report(s).
          {estateResult.failed?.length > 0 && (
            <> <b>{estateResult.failed.length} failed:</b> {estateResult.failed.slice(0, 3).join(' · ')}</>
          )}
          {estateResult.skipped?.length > 0 && (
            <> <span className="muted">{estateResult.skipped.length} skipped (unrecognised format).</span></>
          )}
        </p>
      )}
      {pack && (
        <p className="summary">
          📦 Pack ready — <b>{pack.etl_mappings_packed}</b> mapping(s) +{' '}
          <b>{pack.reports_packed}</b> report(s), {(pack.bytes / 1048576).toFixed(1)} MB.
          {pack.failures?.length > 0 && <> {pack.failures.length} item(s) failed (listed in the manifest).</>}{' '}
          <a className="portfolio-link" href={pack.download}>⬇ Download</a>
        </p>
      )}
      <Explain>
        The whole engagement in one place — every artifact <b>batch-converted</b>
        into the store (<code>pentaho-migrate batch</code> for ETL exports,
        <code> report-batch</code> for Crystal dumps). Each source family
        carries its <b>own</b> effort and cost summary. Track artifacts through
        <b> converted → in review → verified</b>; click an ETL mapping to
        reopen its full conversion.
      </Explain>
      {filtered && (
        <p className="summary">
          Showing the <b>{context}</b> portfolio (matches what is loaded in the
          workflow) — <button className="ghost inline-btn" onClick={() => setShowAll(true)}>show everything</button>
        </p>
      )}
      {showAll && context && (
        <p className="summary">
          Showing all families — <button className="ghost inline-btn" onClick={() => setShowAll(false)}>back to {context} only</button>
        </p>
      )}
    </section>

    {families.filter((f) => visible(f.key)).map((f) => (
      <EtlFamilyCard key={f.key} family={f} />
    ))}

    {reports.length > 0 && visible('crystal') && (
      <section className="card">
        <header>
          <h2>Crystal Reports <span>
            {shownReports.length === reports.length
              ? `${reports.length} converted`
              : `${shownReports.length} of ${reports.length}`}
          </span></h2>
          <div className="triage-bar">
            <input
              className="jndi-input"
              placeholder="JNDI for SQL check (optional)"
              value={jndi}
              onChange={(e) => setJndi(e.target.value)}
              title="With a JNDI name the triage also EXPLAIN-validates each report's SQL against that live connection"
            />
            <button className="primary" onClick={runTriage} disabled={triaging}>
              {triaging ? 'Triaging…' : '🔎 Run triage'}
            </button>
            <a
              className="ghost portfolio-link"
              href={`/project/reports/portfolio?jndi=${encodeURIComponent(jndi)}&rate=${encodeURIComponent(localStorage.getItem('consultantRate') || '150')}`}
              target="_blank"
              rel="noreferrer"
              title="Self-contained HTML consultant report: verdict charts, TODO breakdown by category, review-load distribution, focus list, $ figures — prints to PDF"
            >
              📊 Consultant report
            </a>
          </div>
        </header>
        {sweep?.kind === 'triage' && (
          <StageBar stage={sweep.stage} stages={sweep.stages}
            done={sweep.done} total={sweep.total} detail={sweep.detail} />
        )}
        <Explain>
          <b>Run triage</b> sweeps every stored report with the batch-triage
          agent: formula counts, TODO placeholders, <b>layout QA lint</b>
          (page overflow, collisions, font clipping) and — with a JNDI name —
          the report SQL <b>EXPLAIN-validated against the live database</b>.
          Verdicts: <b>✓ READY</b> (convert-and-go), <b>⚠ REVIEW</b> (click
          the chip for the exact review reasons), <b>✋ BLOCKED</b> (SQL fails
          or the dump no longer parses). <b>Parity</b> takes the customer's
          original Crystal export (PDF or CSV) per report and diffs the real
          numbers rendered from the converted .prpt — PASS / NEAR / FAIL.
          Re-run triage after re-converting; verdicts persist in the store.
        </Explain>
        <div className="filters report-filters">
          {VERDICTS.map((v) => {
            const n = v.key === 'all'
              ? reports.length
              : reports.filter((r) => (r.triage_verdict || 'NONE') === v.key).length
            return (
              <button
                key={v.key}
                className={reportVerdict === v.key ? 'active' : ''}
                onClick={() => setReportVerdict(v.key)}
                disabled={n === 0 && v.key !== 'all'}
              >
                {v.label} {n}
              </button>
            )
          })}
          <input
            className="jndi-input report-search"
            placeholder="Filter by report or file name…"
            value={reportQuery}
            onChange={(e) => setReportQuery(e.target.value)}
          />
          {(reportQuery || reportVerdict !== 'all') && (
            <button onClick={() => { setReportQuery(''); setReportVerdict('all') }}>
              clear
            </button>
          )}
        </div>
        <StatsStrip list={shownReports} />
        {agentError && <div className="error">{agentError}</div>}
        <div className="table-scroll">
          <table className="project-table">
            <thead>
              <tr>
                <th>Report</th><th>Dump file</th>
                <th title="Batch-triage verdict — click a chip for reasons">Triage</th>
                <th title="Release-gate verdict — rendered original vs rendered conversion (runs from the Download page)">Gate</th>
                <th title="Output parity vs the customer's Crystal export (upload PDF/CSV)">Parity</th>
                <th className="num" title="Formulas translated deterministically">✓ auto</th>
                <th className="num" title="Formulas needing a human glance">⚠ review</th>
                <th className="num" title="Formulas to rebuild by hand">✋ manual</th>
                <th className="num" title="TODO placeholders (subreports, images, cross-tabs)">TODOs</th>
                <th className="num" title="Estimated hours saved vs a manual rebuild">Saved</th>
                <th>Status</th><th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {shownReports.map((r) => {
                const detail = triageDetail(r)
                const reasons = detail.reasons || []
                return (
                <React.Fragment key={r.file}>
                <tr>
                  <td className="cell-clip" title={r.name}>{r.name}</td>
                  <td className="notes cell-clip" title={r.file}>{r.file}</td>
                  <td>
                    {r.triage_verdict ? (
                      <button
                        className={`triage-chip verdict-${r.triage_verdict.toLowerCase()}`}
                        title={reasons.length ? 'Show review reasons' : 'No findings'}
                        onClick={() => setExpanded(expanded === r.file ? null : r.file)}
                      >
                        {TRIAGE_ICON[r.triage_verdict] || ''} {r.triage_verdict}
                        {reasons.length > 0 && ` (${reasons.length})`}
                      </button>
                    ) : <span className="muted">—</span>}
                  </td>
                  <td>
                    {r.gate_verdict
                      ? <span className={r.gate_verdict === 'SHIP' ? 'gate-ship' : 'gate-review'}
                          title={gateSummary(r)}>
                          {r.gate_verdict === 'SHIP' ? '✅ SHIP' : '⚠ REVIEW'}
                        </span>
                      : <span className="muted">—</span>}
                  </td>
                  <td>
                    {parityBusy === r.file ? (
                      <span className="muted">checking…</span>
                    ) : r.parity_verdict ? (
                      <span
                        className={`triage-chip parity-${r.parity_verdict.toLowerCase()}`}
                        title={r.parity_note}
                      >
                        {r.parity_verdict}
                      </span>
                    ) : (
                      <label className="parity-upload" title="Upload the customer's Crystal export (PDF or CSV) to diff the numbers">
                        📄 check
                        <input
                          type="file"
                          accept=".pdf,.csv"
                          style={{ display: 'none' }}
                          onChange={(e) => { runParity(r, e.target.files[0]); e.target.value = '' }}
                        />
                      </label>
                    )}
                  </td>
                  <td className="num">{r.formulas_auto}</td>
                  <td className="num">{r.formulas_review}</td>
                  <td className="num">{r.formulas_manual}</td>
                  <td className="num">{r.todos}</td>
                  <td className="num saved-cell">
                    {r.manual_hours > r.copilot_hours
                      ? `${Math.round((r.manual_hours - r.copilot_hours) * 2) / 2}h` : '—'}
                  </td>
                  <td>
                    <select
                      className="status-select"
                      value={r.status}
                      onChange={(e) => updateReportStatus(r, e.target.value)}
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>{s.replace('_', ' ')}</option>
                      ))}
                    </select>
                  </td>
                  <td className="cell-time">{r.updated_at.slice(0, 16)}</td>
                </tr>
                {expanded === r.file && (
                  <tr className="triage-detail-row">
                    <td colSpan={11}>
                      <div className="triage-detail">
                        {detail.sql_status && (
                          <p className={`sql-line sql-${detail.sql_status}`}>
                            SQL vs live DB: <b>{detail.sql_status}</b>
                            {detail.sql_error ? ` — ${detail.sql_error}` : ''}
                          </p>
                        )}
                        {reasons.length ? (
                          <ul>
                            {reasons.map((reason, i) => <li key={i}>{reason}</li>)}
                          </ul>
                        ) : <p className="muted">No findings — ready to hand over.</p>}
                      </div>
                    </td>
                  </tr>
                )}
                </React.Fragment>
              )})}
            </tbody>
          </table>
        </div>
      </section>
    )}
    </>
  )
}

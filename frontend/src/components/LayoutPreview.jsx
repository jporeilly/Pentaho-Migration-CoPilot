// Layout wireframe of the parsed Crystal report: bands stacked in print
// order, every element at its real position and size (points, straight from
// the .rpt). The generated .prpt receives exactly this geometry, so one
// wireframe previews both source and target layout. A design-time view —
// use the PDF preview for the engine-rendered version.

import { useId, useState } from 'react'

const BAND_ORDER = ['ReportHeader', 'PageHeader', 'GroupHeader', 'Detail',
  'GroupFooter', 'ReportFooter', 'PageFooter']

const KIND_COLORS = {
  label: 'var(--text-muted)',
  field: 'var(--accent)',
  special: 'var(--accent)',
  line: 'var(--baseline)',
  box: 'var(--baseline)',
  unknown: 'var(--status-serious)',
  subreport: 'var(--status-serious)',
  image: 'var(--status-warning)',
}

// Report bands are wide and short (a 17pt detail row on an 806pt page), so
// when the SVG scales to fit the card width the height collapses. Give the
// vertical axis a schematic stretch — column x-positions stay 1:1 so header
// and data alignment (what a report reviewer checks) reads true.
const SCALE_Y = 2.2
const BAND_GAP = 4

// A chart band can be 440pt on its own. At the schematic stretch a report like
// that draws four thousand pixels tall, so the reviewer scrolls past acres of
// one rectangle and never sees the shape of the report. Long reports therefore
// open scaled to fit, with the stretch one click away.
const VIEWPORT_H = 620
const MIN_SCALE_Y = 0.35

// When a report has converted subreports, tab between the main report and
// each subreport's own bands (a subreport is a nested banded report).
export function TabbedLayoutPreview({ sections, subreports = [] }) {
  const [tab, setTab] = useState(0)
  if (!subreports.length) return <LayoutPreview sections={sections} />
  const tabs = [{ name: 'Main report', sections },
    ...subreports.map((s) => ({ name: `▸ ${s.name}${s.linked ? ' 🔗' : ''}`, sections: s.sections }))]
  const active = tabs[Math.min(tab, tabs.length - 1)]
  return (
    <div>
      <div className="wf-tabs">
        {tabs.map((t, i) => (
          <button key={i} className={i === tab ? 'active' : ''} onClick={() => setTab(i)}>
            {t.name}
          </button>
        ))}
      </div>
      <LayoutPreview sections={active.sections} />
      {tab > 0 && (
        <p className="muted wf-sub-note">
          Subreport — converts to a nested PRD sub-report bundle
          {active.name.includes('🔗') ? ', linked to the parent row by parameter' : ' (unlinked)'}.
        </p>
      )}
    </div>
  )
}

export default function LayoutPreview({ sections }) {
  const ordered = [...sections].sort(
    (a, b) => BAND_ORDER.indexOf(a.area) - BAND_ORDER.indexOf(b.area) || (a.group ?? 0) - (b.group ?? 0))
  const visible = ordered.filter((s) => !s.suppressed)
  const width = Math.max(560,
    ...visible.flatMap((s) => s.items.map((el) => el.x + el.width))) + 10
  const LABEL_W = 92

  const totalPt = visible.reduce((sum, s) => sum + Math.max(s.height, 14), 0)
    + BAND_GAP * visible.length
  const fitScale = Math.max(MIN_SCALE_Y, VIEWPORT_H / Math.max(totalPt, 1))
  const overflows = totalPt * SCALE_Y > VIEWPORT_H
  const [fit, setFit] = useState(true)
  const scaleY = fit && overflows ? Math.min(SCALE_Y, fitScale) : SCALE_Y

  // labels CLIP to their element's box - a name longer than its field
  // can never spill into the neighbour (CUSTOMERNAME over the next box)
  const clipBase = useId()

  let y = 0
  const bands = visible.map((s) => {
    const h = Math.max(s.height, 14) * scaleY
    const band = { ...s, y, h }
    y += h + BAND_GAP
    return band
  })

  return (
    <div className={`wireframe${fit && overflows ? ' wf-fit' : ''}`}>
      {overflows && (
        <div className="wf-zoom">
          <button className={fit ? 'active' : ''} onClick={() => setFit(true)}>Fit report</button>
          <button className={fit ? '' : 'active'} onClick={() => setFit(false)}>Actual detail</button>
          <span className="muted">
            {Math.round(totalPt)}pt of bands — {fit ? 'scaled to fit' : 'scroll to read'}
          </span>
        </div>
      )}
      <svg viewBox={`0 0 ${width + LABEL_W} ${y + 4}`} width={width + LABEL_W}
        style={{ minHeight: Math.min(y + 4, VIEWPORT_H) }}>
        {bands.map((band, i) => (
          <g key={i} transform={`translate(0 ${band.y})`}>
            <rect x={LABEL_W} y="0" width={width} height={band.h}
              fill="var(--surface-2)" stroke="var(--gridline)" strokeWidth="1" />
            <text x={LABEL_W - 8} y={band.h / 2 + 4} textAnchor="end"
              fill="var(--text-muted)" fontSize="11" fontFamily="system-ui">
              {band.area}{band.group !== null && band.group !== undefined ? ` G${band.group + 1}` : ''}
            </text>
            {band.items.map((el, j) => {
              const color = KIND_COLORS[el.kind] || 'var(--text-muted)'
              const ey = el.y * scaleY
              const eh = Math.max(el.height * scaleY, fit ? 4 : 8)
              if (el.kind === 'line') {
                return <line key={j} x1={LABEL_W + el.x} y1={ey + 1} x2={LABEL_W + el.x + el.width} y2={ey + 1}
                  stroke={color} strokeWidth="1" />
              }
              return (
                <g key={j} opacity={el.layered ? 0.55 : 1}>
                  <rect x={LABEL_W + el.x} y={ey} width={Math.max(el.width, 2)} height={eh}
                    fill={el.kind === 'field' || el.kind === 'special' ? 'rgba(57,135,229,0.12)' : 'none'}
                    stroke={color} strokeWidth="0.8" rx="1.5"
                    strokeDasharray={el.layered ? '3 2' : undefined}>
                    <title>{el.layered
                      ? `${el.kind}: ${el.label} — layered: shows only when its visibility condition matches the row`
                      : `${el.kind}: ${el.label}`}</title>
                  </rect>
                  {el.layered && el.width >= 14 && eh >= 8 && (
                    <text x={LABEL_W + el.x + Math.max(el.width, 2) - 4} y={ey + 8}
                      textAnchor="end" fontSize="7.5" fill="var(--text-muted)"
                      fontFamily="system-ui">▤</text>
                  )}
                  {eh >= 10 && el.width >= 24 && (
                    <>
                      <clipPath id={`${clipBase}-${i}-${j}`}>
                        <rect x={LABEL_W + el.x} y={ey}
                          width={Math.max(el.width - 2, 2)} height={eh} />
                      </clipPath>
                      <text x={LABEL_W + el.x + 3} y={ey + Math.min(eh - 4, 12)}
                        clipPath={`url(#${clipBase}-${i}-${j})`}
                        fill={el.kind === 'unknown' ? 'var(--status-serious)' : 'var(--text-secondary)'}
                        fontSize="8.5" fontFamily="system-ui">
                        {el.label.slice(0, Math.ceil(el.width / 4))}
                      </text>
                    </>
                  )}
                </g>
              )
            })}
          </g>
        ))}
      </svg>
      <div className="wf-legend">
        <span><span className="wf-swatch" style={{ background: 'var(--accent)' }} /> field / special</span>
        <span><span className="wf-swatch" style={{ background: 'var(--text-muted)' }} /> label</span>
        <span><span className="wf-swatch" style={{ background: 'var(--status-warning)' }} /> image</span>
        <span><span className="wf-swatch wf-swatch-layered" /> ▤ layered — one prints per row</span>
        <span><span className="wf-swatch" style={{ background: 'var(--status-serious)' }} /> TODO / subreport</span>
        <span>suppressed bands hidden · positions in points from the .rpt</span>
      </div>
    </div>
  )
}

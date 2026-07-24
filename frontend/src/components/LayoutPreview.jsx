// Layout wireframe of the parsed Crystal report: bands stacked in print
// order, every element at its real position and size (points, straight from
// the .rpt). The generated .prpt receives exactly this geometry, so one
// wireframe previews both source and target layout. A design-time view —
// use the PDF preview for the engine-rendered version.

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

export default function LayoutPreview({ sections }) {
  const ordered = [...sections].sort(
    (a, b) => BAND_ORDER.indexOf(a.area) - BAND_ORDER.indexOf(b.area) || (a.group ?? 0) - (b.group ?? 0))
  const visible = ordered.filter((s) => !s.suppressed)
  const width = Math.max(560,
    ...visible.flatMap((s) => s.items.map((el) => el.x + el.width))) + 10
  const LABEL_W = 92
  let y = 0
  const bands = visible.map((s) => {
    const h = Math.max(s.height, 16)
    const band = { ...s, y, h }
    y += h + 2
    return band
  })

  return (
    <div className="wireframe">
      <svg viewBox={`0 0 ${width + LABEL_W} ${y + 4}`} width={width + LABEL_W}>
        {bands.map((band, i) => (
          <g key={i} transform={`translate(0 ${band.y})`}>
            <rect x={LABEL_W} y="0" width={width} height={band.h}
              fill="var(--surface-2)" stroke="var(--gridline)" strokeWidth="1" />
            <text x={LABEL_W - 8} y={Math.min(band.h / 2 + 3, 12)} textAnchor="end"
              fill="var(--text-muted)" fontSize="8" fontFamily="system-ui">
              {band.area}{band.group !== null && band.group !== undefined ? ` G${band.group + 1}` : ''}
            </text>
            {band.items.map((el, j) => {
              const color = KIND_COLORS[el.kind] || 'var(--text-muted)'
              if (el.kind === 'line') {
                return <line key={j} x1={LABEL_W + el.x} y1={el.y + 1} x2={LABEL_W + el.x + el.width} y2={el.y + 1}
                  stroke={color} strokeWidth="1" />
              }
              return (
                <g key={j}>
                  <rect x={LABEL_W + el.x} y={el.y} width={Math.max(el.width, 2)} height={Math.max(el.height, 4)}
                    fill={el.kind === 'field' || el.kind === 'special' ? 'rgba(57,135,229,0.12)' : 'none'}
                    stroke={color} strokeWidth="0.8" rx="1.5">
                    <title>{el.kind}: {el.label}</title>
                  </rect>
                  {el.height >= 8 && el.width >= 28 && (
                    <text x={LABEL_W + el.x + 2.5} y={el.y + Math.min(el.height - 2, 9)}
                      fill={el.kind === 'unknown' ? 'var(--status-serious)' : 'var(--text-secondary)'}
                      fontSize="6.5" fontFamily="system-ui">
                      {el.label.slice(0, Math.floor(el.width / 4))}
                    </text>
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
        <span><span className="wf-swatch" style={{ background: 'var(--status-serious)' }} /> TODO / subreport</span>
        <span>suppressed bands hidden · positions in points from the .rpt</span>
      </div>
    </div>
  )
}

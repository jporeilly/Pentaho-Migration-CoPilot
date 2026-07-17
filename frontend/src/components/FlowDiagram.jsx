const STATUS = {
  auto:   { color: 'var(--status-good)',    icon: '✓', label: 'auto' },
  review: { color: 'var(--status-warning)', icon: '⚠', label: 'review' },
  manual: { color: 'var(--status-serious)', icon: '✋', label: 'manual' },
}

const NODE_W = 176
const NODE_H = 56
const GAP_X = 64
const GAP_Y = 26
const PAD = 16

// Longest-path layering: a step's column is one past its furthest upstream step.
function layout(pipeline) {
  const layers = {}
  const incoming = {}
  pipeline.steps.forEach((s) => { layers[s.name] = 0; incoming[s.name] = [] })
  pipeline.hops.forEach((h) => incoming[h.to_step]?.push(h.from_step))

  for (let i = 0; i < pipeline.steps.length; i++) {
    let changed = false
    for (const step of pipeline.steps) {
      for (const src of incoming[step.name]) {
        if (layers[step.name] < layers[src] + 1) {
          layers[step.name] = layers[src] + 1
          changed = true
        }
      }
    }
    if (!changed) break
  }

  const byLayer = {}
  pipeline.steps.forEach((s) => {
    (byLayer[layers[s.name]] ??= []).push(s)
  })

  const pos = {}
  const maxRows = Math.max(...Object.values(byLayer).map((l) => l.length))
  Object.entries(byLayer).forEach(([layer, steps]) => {
    const offset = ((maxRows - steps.length) * (NODE_H + GAP_Y)) / 2
    steps.forEach((s, row) => {
      pos[s.name] = {
        x: PAD + layer * (NODE_W + GAP_X),
        y: PAD + offset + row * (NODE_H + GAP_Y),
        step: s,
      }
    })
  })

  const width = PAD * 2 + (Object.keys(byLayer).length) * (NODE_W + GAP_X) - GAP_X
  const height = PAD * 2 + maxRows * (NODE_H + GAP_Y) - GAP_Y
  return { pos, width, height }
}

export default function FlowDiagram({ pipeline, mode = 'pdi' }) {
  if (!pipeline.steps.length) return null
  const { pos, width, height } = layout(pipeline)
  const isSource = mode === 'source'

  return (
    <div className="flow-wrap">
      <svg width={width} height={height} role="img"
           aria-label={`${isSource ? 'Source' : 'Converted'} pipeline flow for ${pipeline.name}`}>
        <defs>
          <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 8 4 L 0 8 z" fill="var(--text-muted)" />
          </marker>
        </defs>

        {pipeline.hops.map((h) => {
          const from = pos[h.from_step]
          const to = pos[h.to_step]
          if (!from || !to) return null
          return (
            <line
              key={`${h.from_step}-${h.to_step}`}
              x1={from.x + NODE_W} y1={from.y + NODE_H / 2}
              x2={to.x - 2} y2={to.y + NODE_H / 2}
              stroke="var(--text-muted)" strokeWidth="1.5" markerEnd="url(#arrow)"
            />
          )
        })}

        {Object.values(pos).map(({ x, y, step }) => {
          const status = STATUS[step.confidence] ?? STATUS.manual
          return (
            <g key={step.name}>
              <title>
                {`${step.name}\n${step.source_type} → ${step.pdi_type ?? 'no mapping'}\nconfidence: ${step.confidence}`}
              </title>
              <rect
                x={x} y={y} width={NODE_W} height={NODE_H} rx="8"
                fill="var(--surface-1)"
                stroke={isSource ? 'var(--baseline)' : status.color}
                strokeWidth="1.75"
              />
              <text x={x + 12} y={y + 23} fill="var(--text-primary)" fontSize="12.5" fontWeight="650">
                {step.name.length > 20 ? step.name.slice(0, 19) + '…' : step.name}
              </text>
              <text x={x + 12} y={y + 41} fill="var(--text-muted)" fontSize="11">
                {isSource ? step.source_type : `${step.source_type} → ${step.pdi_type ?? '(manual)'}`}
              </text>
              {!isSource && (
                <text x={x + NODE_W - 18} y={y + 23} fill={status.color} fontSize="12">
                  {status.icon}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      {!isSource && (
        <div className="flow-legend">
          {Object.values(STATUS).map((s) => (
            <span className="chip" key={s.label} style={{ color: s.color }}>
              {s.icon} {s.label}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

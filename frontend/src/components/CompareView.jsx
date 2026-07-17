import FlowDiagram from './FlowDiagram.jsx'
import { toolLabel } from './SourceBadge.jsx'

// Stacked comparison: original source structure above, converted PDI pipeline
// below. Same layout in both diagrams so steps line up vertically.
export default function CompareView({ pipeline }) {
  return (
    <div className="compare">
      <div className="compare-col">
        <h3 className="subhead">Source — {toolLabel(pipeline.source_tool)}</h3>
        <FlowDiagram pipeline={pipeline} mode="source" />
      </div>
      <div className="compare-col">
        <h3 className="subhead">Converted — Pentaho Data Integration</h3>
        <FlowDiagram pipeline={pipeline} />
      </div>
    </div>
  )
}

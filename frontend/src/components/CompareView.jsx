import FlowDiagram from './FlowDiagram.jsx'

// Side-by-side comparison: original Informatica structure vs converted PDI
// pipeline. Same layout in both diagrams so steps line up visually.
export default function CompareView({ pipeline }) {
  return (
    <div className="compare">
      <div className="compare-col">
        <h3 className="subhead">Source — Informatica PowerCenter</h3>
        <FlowDiagram pipeline={pipeline} mode="source" />
      </div>
      <div className="compare-col">
        <h3 className="subhead">Converted — Pentaho Data Integration</h3>
        <FlowDiagram pipeline={pipeline} />
      </div>
    </div>
  )
}

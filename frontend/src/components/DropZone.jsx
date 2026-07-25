import { useState } from 'react'

export default function DropZone({ onFile, onSample, onTalendSample, onCrystalSample }) {
  const [over, setOver] = useState(false)

  return (
    <div className="uploader">
      <label
        className={`drop${over ? ' over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          if (e.dataTransfer.files.length) onFile(e.dataTransfer.files[0])
        }}
      >
        <input
          type="file"
          accept=".xml,.item"
          onChange={(e) => e.target.files.length && onFile(e.target.files[0])}
        />
        Drop a PowerCenter .xml, Talend .item, or Crystal Reports RptToXml dump here, or{' '}
        <strong>browse</strong> — the format is auto-detected
      </label>
      <div className="sample-row">
        <button className="ghost" onClick={onSample}>Try Informatica</button>
        {onTalendSample && (
          <button className="ghost" onClick={onTalendSample}>Try Talend</button>
        )}
        {onCrystalSample && (
          <button className="ghost" onClick={onCrystalSample}>Try Crystal Reports</button>
        )}
      </div>
    </div>
  )
}

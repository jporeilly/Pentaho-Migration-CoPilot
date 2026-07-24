import { useState } from 'react'

export default function DropZone({ onFile, onSample, onCrystalSample }) {
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
      <span className="sample-buttons">
        <button className="ghost" onClick={onSample}>Try the ETL sample</button>
        {onCrystalSample && (
          <button className="ghost" onClick={onCrystalSample}>Try the Crystal sample</button>
        )}
      </span>
    </div>
  )
}

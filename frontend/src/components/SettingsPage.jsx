import { useCallback, useEffect, useRef, useState } from 'react'

export default function SettingsPage() {
  const [data, setData] = useState(null)       // { settings, detection }
  const [form, setForm] = useState(null)       // editable copy of settings
  const [saved, setSaved] = useState(false)
  const [pull, setPull] = useState({ status: 'idle', detail: '' })
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/settings')
      if (!res.ok) throw new Error(res.statusText)
      const body = await res.json()
      setData(body)
      setForm(body.settings)
    } catch (err) {
      setError(`Could not load settings: ${err.message}`)
    }
  }, [])

  useEffect(() => {
    refresh()
    return () => clearInterval(pollRef.current)
  }, [refresh])

  async function save(next) {
    const settings = next ?? form
    const res = await fetch('/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    })
    if (res.ok) {
      setForm(await res.json())
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    }
  }

  function applyRecommendation() {
    const rec = data.detection.recommendation
    save({
      ...form,
      provider: 'ollama',
      base_url: data.detection.ollama.base_url,
      model: rec.model,
      env: rec.env_suggestions,
    })
  }

  async function pullModel(model) {
    await fetch(`/settings/ollama/pull?model=${encodeURIComponent(model)}`, { method: 'POST' })
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      const state = await (await fetch('/settings/ollama/pull')).json()
      setPull(state)
      if (state.status === 'done' || state.status === 'error') {
        clearInterval(pollRef.current)
        if (state.status === 'done') refresh()
      }
    }, 1500)
  }

  if (error) return <div className="error">{error}</div>
  if (!data || !form) return <p className="loading">Detecting environment…</p>

  const { detection } = data
  const { ollama, recommendation } = detection
  const recInstalled = ollama.installed_models.some((m) => m.startsWith(recommendation.model))

  return (
    <div className="settings">
      <div className="settings-grid">
        <section className="card">
          <h2>Environment</h2>
          <dl>
            <dt>Platform</dt><dd>{detection.platform}</dd>
            <dt>RAM</dt><dd>{detection.ram_gb ? `${detection.ram_gb} GB` : 'unknown'}</dd>
            <dt>GPU</dt>
            <dd>{detection.gpu_name ? `${detection.gpu_name} (${detection.vram_gb} GB VRAM)` : 'no NVIDIA GPU detected'}</dd>
            <dt>Ollama</dt>
            <dd>
              {ollama.running
                ? <span className="ok">✓ running v{ollama.version} at {ollama.base_url}</span>
                : <span className="warn">⚠ not reachable at {ollama.base_url} — install from ollama.com and start it</span>}
            </dd>
            <dt>ANTHROPIC_API_KEY</dt>
            <dd>{detection.anthropic_key_present ? '✓ present' : 'not set'}</dd>
          </dl>
          {Object.keys(detection.env).length > 0 && (
            <>
              <h3>OLLAMA_* environment variables</h3>
              <dl>
                {Object.entries(detection.env).map(([k, v]) => (
                  <div key={k} className="pair"><dt>{k}</dt><dd>{v}</dd></div>
                ))}
              </dl>
            </>
          )}
        </section>

        <section className="card recommend">
          <h2>Recommended setup</h2>
          <p className="rec-model">{recommendation.model}</p>
          <p className="rec-reason">{recommendation.reason}</p>
          {Object.keys(recommendation.env_suggestions).length > 0 && (
            <>
              <h3>Suggested Ollama tuning</h3>
              <dl>
                {Object.entries(recommendation.env_suggestions).map(([k, v]) => (
                  <div key={k} className="pair"><dt>{k}</dt><dd>{v}</dd></div>
                ))}
              </dl>
            </>
          )}
          <div className="actions">
            <button className="primary" onClick={applyRecommendation}>
              Apply recommendation
            </button>
            {ollama.running && !recInstalled && (
              <button className="ghost" onClick={() => pullModel(recommendation.model)}>
                Pull {recommendation.model}
              </button>
            )}
          </div>
          {pull.status !== 'idle' && (
            <p className={`pull-status ${pull.status}`}>
              {pull.status === 'error' ? '⚠ ' : ''}{pull.detail}
            </p>
          )}
        </section>
      </div>

      <section className="card">
        <h2>LLM settings</h2>
        <div className="form-grid">
          <label>
            Provider
            <select
              value={form.provider}
              onChange={(e) => setForm({ ...form, provider: e.target.value })}
            >
              <option value="ollama">Ollama (local)</option>
              <option value="anthropic">Anthropic API</option>
              <option value="none">Disabled</option>
            </select>
          </label>
          {form.provider === 'ollama' && (
            <>
              <label>
                Base URL
                <input
                  value={form.base_url}
                  onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                />
              </label>
              <label>
                Model
                <select
                  value={form.model ?? ''}
                  onChange={(e) => setForm({ ...form, model: e.target.value || null })}
                >
                  <option value="">— choose a model —</option>
                  {!ollama.installed_models.includes(form.model) && form.model && (
                    <option value={form.model}>{form.model} (not installed)</option>
                  )}
                  {ollama.installed_models.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </label>
            </>
          )}
          {form.provider === 'anthropic' && (
            <p className="hint">
              Uses the ANTHROPIC_API_KEY environment variable
              ({detection.anthropic_key_present ? '✓ detected' : '⚠ not set'}).
              The key itself is never stored or displayed.
            </p>
          )}
        </div>
        <div className="actions">
          <button className="primary" onClick={() => save()}>Save settings</button>
          {saved && <span className="ok">✓ saved</span>}
        </div>
      </section>
    </div>
  )
}

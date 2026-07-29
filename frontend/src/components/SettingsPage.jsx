import { useCallback, useEffect, useRef, useState } from 'react'
import ThemeSelect from './ThemeSelect.jsx'
import DatabaseDriversCard from './DatabaseDriversCard.jsx'

// Mirrors CLOUD_PROVIDERS in llm/translate.py (labels + env var + model hint).
const CLOUD_PROVIDERS = {
  anthropic: { label: 'Anthropic (Claude)', env: 'ANTHROPIC_API_KEY', modelHint: 'claude-opus-5 (default)' },
  openai: { label: 'OpenAI (GPT)', env: 'OPENAI_API_KEY', modelHint: 'gpt-4o (default)' },
  google: { label: 'Google (Gemini)', env: 'GEMINI_API_KEY', modelHint: 'gemini-1.5-pro (default)' },
  azure: { label: 'Microsoft (Azure OpenAI)', env: 'AZURE_OPENAI_API_KEY', modelHint: 'your deployment name' },
}

export default function SettingsPage({ onBack }) {
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
      <button className="ghost back-btn" onClick={onBack}>← Back to workflow</button>
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
            {Object.entries(CLOUD_PROVIDERS).map(([key, spec]) => (
              <div key={key} className="pair">
                <dt>{spec.env}</dt>
                <dd>{detection.cloud_keys?.[key] ? '✓ present' : 'not set'}</dd>
              </div>
            ))}
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
        <p className="hint">
          One provider powers every AI feature: Informatica / Talend expression
          translation, Crystal Reports formula translation, and the schema-SQL
          assistant.
        </p>
        <div className="form-grid">
          <label>
            Provider
            <select
              value={form.provider}
              onChange={(e) => {
                const provider = e.target.value
                // base_url is provider-specific: reset it when switching so an
                // Ollama URL never leaks into a cloud provider (and back).
                const base_url = provider === 'ollama'
                  ? (ollama.base_url || 'http://127.0.0.1:11434')
                  : ''
                setForm({ ...form, provider, base_url, model: null })
              }}
            >
              <option value="ollama">Ollama (local)</option>
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="openai">OpenAI (GPT)</option>
              <option value="google">Google (Gemini)</option>
              <option value="azure">Microsoft (Azure OpenAI)</option>
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
          {CLOUD_PROVIDERS[form.provider] && (
            <>
              <label>
                API key
                <input
                  type="password"
                  placeholder={detection.cloud_keys?.[form.provider]
                    ? `using ${CLOUD_PROVIDERS[form.provider].env} from environment`
                    : `paste key, or set ${CLOUD_PROVIDERS[form.provider].env}`}
                  value={form.api_key ?? ''}
                  onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                  autoComplete="off"
                />
              </label>
              <label>
                {form.provider === 'azure' ? 'Deployment name' : 'Model'}
                <input
                  placeholder={CLOUD_PROVIDERS[form.provider].modelHint}
                  value={form.model ?? ''}
                  onChange={(e) => setForm({ ...form, model: e.target.value || null })}
                />
              </label>
              {form.provider === 'azure' && (
                <label>
                  Resource endpoint
                  <input
                    placeholder="https://<resource>.openai.azure.com"
                    value={form.base_url}
                    onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                  />
                </label>
              )}
              <p className="hint">
                {CLOUD_PROVIDERS[form.provider].env}:{' '}
                {detection.cloud_keys?.[form.provider] ? '✓ detected in environment' : 'not set in environment'}.
                A key saved here is stored locally in config/settings.json and
                takes precedence over the environment variable. Keys are only
                ever sent to the provider's own API.
              </p>
            </>
          )}
        </div>
        <div className="actions">
          <button className="primary" onClick={() => save()}>Save settings</button>
          {saved && <span className="ok">✓ saved</span>}
        </div>
      </section>

      <DatabaseDriversCard />

      <section className="card">
        <h2>Appearance</h2>
        <div className="form-grid">
          <label>
            Color theme
            <ThemeSelect />
          </label>
        </div>
      </section>
    </div>
  )
}

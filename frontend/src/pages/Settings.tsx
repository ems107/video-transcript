import { useEffect, useState } from 'react'
import { api, type Settings } from '../api'

const FIELDS: { key: string; label: string; help?: string; type?: 'number' | 'select'; options?: [string, string][] }[] = [
  { key: 'analyzed_dir', label: 'Carpeta de vídeos analizados', help: 'Cada vídeo se publica en una subcarpeta «AAAA-MM-DD - Título».' },
  { key: 'file_mode', label: 'Vídeo original', type: 'select', options: [['move', 'Mover a su carpeta'], ['copy', 'Copiar (no tocar el original)']] },
  { key: 'owner_name', label: 'Tu nombre', help: 'Se usa cuando hay pista separada de micrófono.' },
  { key: 'whisper_batch_size', label: 'Lote de Whisper', type: 'number', help: 'Bájalo si hay errores de memoria de GPU.' },
  { key: 'voice_match_threshold', label: 'Umbral para proponer persona por voz (0-1)', type: 'number' },
  { key: 'voice_auto_threshold', label: 'Umbral de alta confianza por voz (0-1)', type: 'number' },
  { key: 'max_frames', label: 'Máximo de fotogramas analizados por vídeo', type: 'number', help: 'Cada fotograma tarda ~8 s en analizarse.' },
  { key: 'frame_max_interval', label: 'Analizar al menos un fotograma cada (s)', type: 'number' },
  { key: 'chunk_minutes', label: 'Minutos por bloque de resumen', type: 'number' },
  { key: 'llm_n_cpu_moe', label: 'Capas MoE del LLM en CPU', type: 'number', help: 'Súbelo si llama-server falla por falta de memoria de GPU; bájalo para más velocidad.' },
  { key: 'llm_ctx', label: 'Contexto del LLM (tokens)', type: 'number' },
  { key: 'llm_model_path', label: 'Modelo LLM (GGUF)' },
  { key: 'llm_mmproj_path', label: 'Proyector de visión (mmproj)' },
  { key: 'llama_server_path', label: 'llama-server.exe' },
  { key: 'diarization_model_dir', label: 'Carpeta de pyannote community-1' },
]

export default function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null)
  const [msg, setMsg] = useState('')

  useEffect(() => { api.get<Settings>('/api/settings').then(setS) }, [])
  if (!s) return <p className="muted">Cargando…</p>

  async function save() {
    try {
      setS(await api.put<Settings>('/api/settings', s))
      setMsg('Guardado. Se aplica a los próximos trabajos.')
    } catch (e) {
      setMsg((e as Error).message)
    }
  }

  return (
    <>
      <h1>Ajustes</h1>
      <div className="card pad stack" style={{ maxWidth: 820 }}>
        {FIELDS.map((f) => (
          <label key={f.key} className="field">
            <span>{f.label}</span>
            {f.type === 'select' ? (
              <select value={String(s[f.key])} onChange={(e) => setS({ ...s, [f.key]: e.target.value })}>
                {f.options!.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            ) : (
              <input type={f.type ?? 'text'} step="any" value={String(s[f.key] ?? '')}
                onChange={(e) => setS({ ...s, [f.key]: f.type === 'number' ? Number(e.target.value) : e.target.value })} />
            )}
            {f.help && <small>{f.help}</small>}
          </label>
        ))}
        <div className="row">
          <button className="primary" onClick={save}>Guardar</button>
          {msg && <span className="small muted">{msg}</span>}
        </div>
      </div>
    </>
  )
}

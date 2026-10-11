import { useState } from 'react'
import { api, type VideoDetail } from './api'

// Correcciones del usuario sobre el análisis de un vídeo. La IA las recibe como hechos al regenerar
export function CorrectionsPanel({ video, running, onChange, onRegenerate }: {
  video: VideoDetail
  running: boolean
  onChange: () => void
  onRegenerate: () => void
}) {
  const [text, setText] = useState('')
  const [editing, setEditing] = useState<{ id: number; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await fn()
      onChange()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card pad" style={{ marginTop: '1rem' }}>
      <h3 style={{ margin: 0 }}>Correcciones</h3>
      <p className="small muted" style={{ marginTop: '0.35rem' }}>
        Lo que el análisis ha interpretado mal, escrito como un hecho. Por ejemplo: «Fulano es quien presenta, no Mengano»
        o «La tarea de enviar el informe no se acordó». Se aplican al regenerar y nunca las modifica la IA.
      </p>
      {video.video_corrections.length > 0 && (
        <ul className="corrections">
          {video.video_corrections.map((c) => (
            <li key={c.id}>
              {editing?.id === c.id ? (
                <div className="row" style={{ flexWrap: 'nowrap' }}>
                  <input value={editing.text} onChange={(e) => setEditing({ ...editing, text: e.target.value })} />
                  <button className="sm" disabled={busy || !editing.text.trim()} onClick={() => act(async () => {
                    await api.put(`/api/corrections/${c.id}`, { text: editing.text })
                    setEditing(null)
                  })}>Guardar</button>
                  <button className="sm" disabled={busy} onClick={() => setEditing(null)}>Cancelar</button>
                </div>
              ) : (
                <div className="spread">
                  <span>{c.text}</span>
                  <span className="row" style={{ gap: '0.35rem', flexWrap: 'nowrap' }}>
                    <button className="sm" disabled={busy} onClick={() => setEditing({ id: c.id, text: c.text })}>Editar</button>
                    <button className="sm danger" disabled={busy}
                      onClick={() => confirm('¿Borrar esta corrección?') && act(() => api.del(`/api/corrections/${c.id}`))}>Borrar</button>
                  </span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="row" style={{ flexWrap: 'nowrap', marginTop: '0.5rem' }}>
        <input placeholder="Añadir una corrección…" value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && text.trim()) act(async () => { await api.post(`/api/videos/${video.id}/corrections`, { text }); setText('') }) }} />
        <button className="sm" disabled={busy || !text.trim()}
          onClick={() => act(async () => { await api.post(`/api/videos/${video.id}/corrections`, { text }); setText('') })}>Añadir</button>
      </div>
      {video.corrections_pending && (
        <div className="notice inline small" style={{ marginTop: '0.75rem' }}>
          <span>Hay correcciones sin aplicar al análisis.</span>
          <button className="sm primary" disabled={running} onClick={onRegenerate}>Regenerar</button>
        </div>
      )}
    </div>
  )
}

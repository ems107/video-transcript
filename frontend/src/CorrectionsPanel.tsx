import { useState } from 'react'
import { api, type VideoDetail } from './api'
import { HelpLink } from './HelpMarkdown'

// Correcciones del usuario sobre el análisis de un vídeo. La IA las recibe como hechos al regenerar
export function CorrectionsPanel({ video, onChange }: { video: VideoDetail; onChange: () => void }) {
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
      <h3 style={{ margin: 0 }}>Correcciones <HelpLink to="correcciones" /></h3>
      <p className="small muted" style={{ marginTop: '0.35rem' }}>
        Escribe aquí lo que el análisis ha interpretado mal, como hechos sobre lo que ocurre en el vídeo. Al aplicar, la
        IA vuelve a escribir el análisis desde cero, sin ver el anterior, y recibe estas correcciones como hechos que
        prevalecen sobre la grabación. Por eso cada corrección debe entenderse por sí sola, sin referirse a partes del
        resumen. Se aplican en cada regeneración: mantenlas aunque el resumen ya salga bien. Afectan al resumen, las tareas
        y el aprendizaje, no al texto de la transcripción; para eso está el glosario del perfil. Para corregir quién es
        un hablante, usa el panel Hablantes: así también se guarda su voz. La IA nunca las modifica.
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
                <div className="correction-row">
                  <span className="grow">{c.text}</span>
                  <span className="actions">
                    <span className={c.applied ? 'pill ok' : 'pill warn'}
                      title={c.applied ? 'El análisis actual ya la tiene en cuenta' : 'Se aplicará con «Aplicar y continuar»'}>
                      {c.applied ? 'Aplicada' : 'Pendiente'}
                    </span>
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
        <div className="notice small" style={{ marginTop: '0.75rem' }}>
          Hay correcciones sin aplicar al análisis: se aplicarán con <b>Aplicar y continuar</b>.
        </div>
      )}
    </div>
  )
}

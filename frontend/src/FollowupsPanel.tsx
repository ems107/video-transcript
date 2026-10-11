import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Followup, type FollowupEvent, type VideoDetail } from './api'
import { EVENT_LABELS } from './followup'
import { HelpLink } from './HelpMarkdown'
import { parseTs } from './util'

// Tarjeta «Seguimientos» de la página del vídeo
export function FollowupsPanel({ video, running, onChange }: { video: VideoDetail; running: boolean; onChange: () => void }) {
  const [adding, setAdding] = useState(false)
  const [detaching, setDetaching] = useState<{ id: number; name: string } | null>(null)
  if (video.status !== 'done') return null
  return (
    <div className="card pad" style={{ marginTop: '1rem' }}>
      <h3 style={{ marginTop: 0 }}>Seguimientos <HelpLink to="seguimientos" /></h3>
      {video.followups.length === 0
        ? <p className="small muted" style={{ marginTop: 0 }}>Si este vídeo continúa un tema de otros vídeos, añádelo a su seguimiento.</p>
        : (
          <ul className="corrections">
            {video.followups.map((f) => (
              <li key={f.id}>
                <div className="correction-row">
                  <span className="grow">
                    <Link to={`/seguimientos/${f.id}`}>{f.name}</Link>
                    {f.status === 'archivado' && <> <span className="pill">archivado</span></>}
                  </span>
                  <span className="actions">
                    {!f.applied && <span className="pill warn" title="El estado del seguimiento aún no incluye este vídeo">sin aplicar</span>}
                    <button className="sm" disabled={running} onClick={() => setDetaching(f)}>Quitar</button>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      <button className="sm" disabled={running} onClick={() => setAdding(true)}>Añadir a un seguimiento</button>
      {adding && <AddDialog video={video} onClose={() => setAdding(false)} onDone={() => { setAdding(false); onChange() }} />}
      {detaching && <DetachDialog followupId={detaching.id} followupName={detaching.name} video={{ id: video.id, title: video.title }}
        onClose={() => setDetaching(null)} onDone={() => { setDetaching(null); onChange() }} />}
    </div>
  )
}

function AddDialog({ video, onClose, onDone }: { video: VideoDetail; onClose: () => void; onDone: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [rows, setRows] = useState<Followup[]>([])
  const [target, setTarget] = useState('')
  const [name, setName] = useState('')
  const [regenerate, setRegenerate] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    ref.current?.showModal()
    api.get<Followup[]>('/api/followups').then((fs) => {
      const inside = new Set(video.followups.map((f) => f.id))
      const open = fs.filter((f) => f.status === 'abierto' && !inside.has(f.id))
      setRows(open)
      setTarget(open.length ? String(open[0].id) : 'nuevo')
    })
  }, [video])

  const run = async () => {
    setBusy(true)
    setError('')
    try {
      let id = Number(target)
      if (target === 'nuevo') id = (await api.post<Followup>('/api/followups', { name })).id
      await api.post(`/api/followups/${id}/videos/${video.id}`, { apply: true, regenerate })
      onDone()
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <dialog ref={ref} className="card dialog" onClose={onClose}>
      <h3>Añadir a un seguimiento <HelpLink to="seguimientos#anadir-videos" /></h3>
      <div className="stack">
        <label className="field">
          <span>Seguimiento</span>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            {rows.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            <option value="nuevo">Nuevo seguimiento…</option>
          </select>
        </label>
        {target === 'nuevo' && (
          <label className="field"><span>Nombre del nuevo seguimiento</span><input autoFocus value={name} onChange={(e) => setName(e.target.value)} /></label>
        )}
        <p className="small muted" style={{ margin: 0 }}>
          La IA aplica el vídeo al estado del seguimiento en su fecha: lo que dice de las tareas, decisiones y dudas
          anteriores, y lo nuevo. Si hay vídeos posteriores, el estado se rehace desde este. No se vuelve a transcribir.
        </p>
        <label className="check">
          <input type="checkbox" checked={regenerate} onChange={(e) => setRegenerate(e.target.checked)} />
          <span>
            <b>Regenerar también el resumen del vídeo</b>
            <span className="small muted">Para que el resumen relacione lo que se dice con lo anterior del tema («continúa lo de…»). Tarda como regenerar el análisis.</span>
          </span>
        </label>
        {error && <p className="small danger-text">{error}</p>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button onClick={() => ref.current?.close()} disabled={busy}>Cancelar</button>
          <button className="primary" onClick={run} disabled={busy || (target === 'nuevo' && !name.trim())}>Añadir</button>
        </div>
      </div>
    </dialog>
  )
}

// Quitar un vídeo de un seguimiento: rehacer el estado sin él o dejarlo como está
export function DetachDialog({ followupId, followupName, video, onClose, onDone }: {
  followupId: number; followupName: string; video: { id: number; title: string }; onClose: () => void; onDone: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [rebuild, setRebuild] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { ref.current?.showModal() }, [])

  const run = async () => {
    setBusy(true)
    try {
      await api.del(`/api/followups/${followupId}/videos/${video.id}?rebuild=${rebuild}`)
      onDone()
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <dialog ref={ref} className="card dialog" onClose={onClose}>
      <h3>Quitar del seguimiento</h3>
      <div className="stack">
        <p className="small" style={{ margin: 0 }}>Quitar «{video.title}» de «{followupName}». El vídeo no se toca.</p>
        <FollowupChoice rebuild={rebuild} onChange={setRebuild}
          rebuildText="Se quita lo que aportó este vídeo y la IA vuelve a aplicar los posteriores. Lo que cambiaste tú se conserva."
          keepText="El estado sigue incluyendo lo que aportó y queda marcado como desactualizado, para rehacerlo cuando quieras." />
        {error && <p className="small danger-text">{error}</p>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button onClick={() => ref.current?.close()} disabled={busy}>Cancelar</button>
          <button className="primary" onClick={run} disabled={busy}>Quitar</button>
        </div>
      </div>
    </dialog>
  )
}

// La pregunta de siempre al cambiar un vídeo de un seguimiento: rehacer el estado o dejarlo como está
export function FollowupChoice({ name, rebuild, onChange, rebuildText, keepText }: {
  name?: string; rebuild: boolean; onChange: (v: boolean) => void; rebuildText: string; keepText: string
}) {
  return (
    <div className="small">
      {name && <b>Seguimiento «{name}»</b>}
      <label className="check">
        <input type="radio" checked={rebuild} onChange={() => onChange(true)} />
        <span><b>Rehacer el estado</b> <span className="muted">{rebuildText}</span></span>
      </label>
      <label className="check">
        <input type="radio" checked={!rebuild} onChange={() => onChange(false)} />
        <span><b>Dejarlo como está</b> <span className="muted">{keepText}</span></span>
      </label>
    </div>
  )
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })
}

// Un hito del recorrido de un punto: fecha y momento del vídeo (con enlace) y qué pasó
export function EventChip({ e }: { e: FollowupEvent }) {
  const label = EVENT_LABELS[e.evento] ?? e.evento
  const where = e.source === 'manual'
    ? <span title={`Cambio tuyo, ${new Date(e.at).toLocaleString('es-ES')}`}>a mano</span>
    : e.date && e.video_id
      ? <Link to={`/videos/${e.video_id}?t=${parseTs(e.t) ?? 0}&tab=resumen`} title={e.video_title || 'Vídeo quitado'}>
          {shortDate(e.date)}{e.t && ` · ${e.t}`}
        </Link>
      : e.date ? <span>{shortDate(e.date)}</span> : null
  return (
    <span className={`event ${e.evento}`}>
      {where}<b>{label}</b>{e.nota && <span className="muted">{e.nota}</span>}
    </span>
  )
}

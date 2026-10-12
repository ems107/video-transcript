import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type ApplyInfo, type Job, type ReviewItem, type VideoDetail } from '../api'
import { EVENT_LABELS, KIND_ONE, STATUS_AFTER } from '../followup'
import { ProposalList } from '../knowledge'
import { HelpLink } from '../HelpMarkdown'
import { fmtDuration, notifyKnowledge } from '../util'
import { JobRow } from './Queue'

// Botón «Aplicar y continuar»: aplica los cambios, guarda las voces, actualiza los seguimientos y propone conocimiento
export function ApplyButton({ video, onDone }: { video: VideoDetail; onDone: () => void }) {
  const [info, setInfo] = useState<ApplyInfo | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    api.get<ApplyInfo>(`/api/videos/${video.id}/apply`).then(setInfo).catch(() => setInfo(null))
  }, [video])
  const label = video.review.changes.length ? 'Aplicar y continuar' : 'Dar por revisado y continuar'
  return (
    <>
      <button className="sm primary" disabled={busy} onClick={async () => {
        setBusy(true)
        setError('')
        try {
          await api.post(`/api/videos/${video.id}/apply`)
          onDone()
        } catch (e) {
          setError((e as Error).message)
        } finally {
          setBusy(false)
        }
      }}>{label}{info ? ` (≈ ${fmtDuration(Math.max(info.seconds, 30))})` : ''}</button>
      {error && <span className="danger-text small">{error}</span>}
    </>
  )
}

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`
}

// Aviso fijo de la página del vídeo mientras no está revisado
export function ReviewBanner({ video, onChange }: { video: VideoDetail; onChange: () => void }) {
  const r = video.review
  if (r.state === 'revisado' || video.status !== 'done') return null
  const waiting = r.waiting.length > 0 && (
    <> {r.waiting.length === 1 ? <>«<Link to={`/videos/${r.waiting[0].id}`}>{r.waiting[0].title}</Link>» espera</>
      : <>{r.waiting.length} vídeos esperan</>} a esta revisión.</>
  )
  if (r.state === 'aplicando') {
    return <div className="notice small" style={{ marginBottom: '1rem' }}><b>Aplicando la revisión…</b> Al terminar, quedará lo dudoso por decidir.</div>
  }
  if (r.state === 'propuestas') {
    const parts = [r.pending.propuestas && plural(r.pending.propuestas, 'propuesta para el perfil', 'propuestas para el perfil'),
      r.pending.seguimiento && plural(r.pending.seguimiento, 'duda del seguimiento', 'dudas del seguimiento')].filter(Boolean)
    return (
      <div className="notice inline small warn-box" style={{ marginBottom: '1rem' }}>
        <span><b>Queda por decidir:</b> {parts.join(' y ')}.{waiting}</span>
        <Link className="btn sm primary" to={`/videos/${video.id}/revisar`}>Decidir</Link>
      </div>
    )
  }
  return (
    <div className="notice inline small warn-box" style={{ marginBottom: '1rem' }}>
      <span>
        <b>Pendiente de revisar.</b> Comprueba los hablantes, la transcripción y el resumen. Hasta que lo apliques, este vídeo
        no actualiza sus seguimientos ni propone nada para el perfil.{waiting}
        {r.changes.length > 0 && <> Sin aplicar: {r.changes.map((c) => c.label).join(', ')}.</>} <HelpLink to="revision" />
      </span>
      <span className="row" style={{ gap: '0.35rem' }}>
        <Link className="btn sm" to={`/videos/${video.id}/revisar`}>Paso a paso</Link>
        <ApplyButton video={video} onDone={onChange} />
      </span>
    </div>
  )
}

// Una duda de la IA sobre un punto del seguimiento: si repite otro o si un cambio sin frase que lo demuestre pasó
function ReviewItemRow({ r, onChange }: { r: ReviewItem; onChange: () => void }) {
  const [busy, setBusy] = useState(false)
  const url = `/api/followups/${r.followup_id}/items/${r.item.id}`
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await fn()
      onChange()
    } finally {
      setBusy(false)
    }
  }
  const p = r.possible
  return (
    <li className="card pad" style={{ marginBottom: '0.5rem' }}>
      <div className="small muted"><Link to={`/seguimientos/${r.followup_id}`}>{r.followup_name}</Link> · {KIND_ONE[r.item.kind]}</div>
      <div><b>{r.item.text}</b>{r.item.owner && <span className="muted"> — {r.item.owner}</span>}</div>
      {r.reasons.includes('duplicado') && (
        <div style={{ marginTop: '0.4rem' }}>
          <div className="small">
            ¿Es lo mismo que {r.same_as ? <>«{r.same_as.text}» ({KIND_ONE[r.same_as.kind]}, {r.same_as.hidden ? 'borrada por ti' : r.same_as.status})</> : 'otro punto'}?
            {r.item.review.motivo && <span className="muted"> La IA duda: {r.item.review.motivo}</span>}
          </div>
          <div className="row" style={{ gap: '0.35rem', marginTop: '0.3rem' }}>
            <button className="sm primary" disabled={busy} onClick={() => act(() => api.post(`${url}/resolve`, { action: 'mismo' }))}>Sí, es lo mismo</button>
            <button className="sm" disabled={busy} onClick={() => act(() => api.post(`${url}/resolve`, { action: 'distinto' }))}>No, es distinto</button>
          </div>
        </div>
      )}
      {p?.posible && (
        <div style={{ marginTop: '0.4rem' }}>
          <div className="small">
            La IA cree que queda <b>{EVENT_LABELS[p.posible]}</b> en {p.t}, pero no encuentra la frase que lo diga.
            {p.nota && <span className="muted"> {p.nota}</span>}
          </div>
          <div className="row" style={{ gap: '0.35rem', marginTop: '0.3rem' }}>
            <button className="sm primary" disabled={busy}
              onClick={() => act(() => api.put(url, { status: STATUS_AFTER[p.posible!] ?? r.item.status }))}>Sí, confirmar</button>
            <button className="sm" disabled={busy} onClick={() => act(() => api.post(`${url}/resolve`, { action: 'descartar' }))}>No pasó</button>
          </div>
        </div>
      )}
    </li>
  )
}

// «Revisar este vídeo»: lo que hay que comprobar y decidir, en orden
export default function Review({ jobs }: { jobs: Job[] }) {
  const { id } = useParams()
  const [video, setVideo] = useState<VideoDetail | null>(null)
  const [items, setItems] = useState<ReviewItem[]>([])
  const load = useCallback(() => {
    api.get<VideoDetail>(`/api/videos/${id}`).then(setVideo)
    api.get<ReviewItem[]>(`/api/videos/${id}/review-items`).then(setItems)
  }, [id])
  useEffect(load, [load])
  useEffect(() => {
    window.addEventListener('knowledge-changed', load)
    return () => window.removeEventListener('knowledge-changed', load)
  }, [load])
  const job = jobs.find((j) => String(j.video_id) === id)
  useEffect(() => { if (job?.status === 'done') load() }, [job?.status, load])

  if (!video) return <p className="muted">Cargando…</p>
  const r = video.review
  const unconfirmed = video.speakers.filter((s) => !s.confirmed)
  const proposed = unconfirmed.filter((s) => s.suggested_person_id || s.suggested_name).length
  const step1 = r.state === 'pendiente'
  const running = job && ['queued', 'running', 'waiting'].includes(job.status)

  return (
    <>
      <div className="muted small"><Link to={`/videos/${video.id}`}>← {video.title}</Link></div>
      <h1>Revisar este vídeo <HelpLink to="revision" /></h1>
      {r.state === 'revisado' && <div className="notice small" style={{ marginBottom: '1rem' }}><b>Revisado.</b> No queda nada por decidir.</div>}
      {running && job && <div style={{ marginBottom: '1rem' }}><JobRow job={job} /></div>}

      <div className="card pad" style={{ marginBottom: '1rem', opacity: step1 ? 1 : 0.7 }}>
        <h3 style={{ marginTop: 0 }}>1. Comprueba el vídeo {!step1 && <span className="pill ok">hecho</span>}</h3>
        <ul className="small">
          <li>
            Hablantes: {unconfirmed.length === 0 ? 'todos confirmados.' : <>{plural(unconfirmed.length, 'sin confirmar', 'sin confirmar')}
              {proposed > 0 && <> ({proposed} con propuesta)</>}. <Link to={`/videos/${video.id}`}>Revísalos</Link>.</>}
            {proposed > 0 && step1 && (
              <> <button className="sm" onClick={async () => {
                await api.post(`/api/videos/${video.id}/confirm-speakers`)
                notifyKnowledge()
                load()
              }}>Aceptar las propuestas</button></>
            )}
          </li>
          <li>
            <Link to={`/videos/${video.id}?tab=transcripcion`}>Transcripción</Link>: si una frase es de otra persona, pulsa su nombre.
            {video.segments.some((s) => s.voice === 'dudosa') && <> Hay tramos con <b>voz dudosa</b>: míralos primero.</>}
          </li>
          <li>
            <Link to={`/videos/${video.id}`}>Resumen y tareas</Link>: lo que esté mal, escríbelo en <b>Correcciones</b>.
          </li>
          {r.changes.length > 0 && <li>Sin aplicar: {r.changes.map((c) => c.label).join(', ')}.</li>}
        </ul>
        {step1 && video.status === 'done' && (
          <div className="row" style={{ gap: '0.5rem' }}>
            <ApplyButton video={video} onDone={load} />
            <span className="small muted">Aplica tus cambios, guarda las voces, actualiza los seguimientos y propone lo aprendido.</span>
          </div>
        )}
      </div>

      <div className="card pad" style={{ opacity: r.state === 'propuestas' ? 1 : 0.7 }}>
        <h3 style={{ marginTop: 0 }}>2. Decide lo dudoso</h3>
        {step1 || r.state === 'aplicando' ? (
          <p className="small muted">Aparecerá al aplicar el paso 1.</p>
        ) : (
          <>
            <h4>Seguimientos</h4>
            {items.length === 0 ? <p className="small muted">Nada que decidir.</p> : (
              <ul style={{ listStyle: 'none', padding: 0 }}>
                {items.map((it) => <ReviewItemRow key={`${it.followup_id}-${it.item.id}`} r={it} onChange={load} />)}
              </ul>
            )}
            <h4>Propuestas para el perfil y las personas</h4>
            <ProposalList query={`video_id=${video.id}`} empty="No hay propuestas pendientes." />
          </>
        )}
      </div>
    </>
  )
}

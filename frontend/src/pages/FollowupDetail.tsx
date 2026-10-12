import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, type FollowupDetail as FD, type FollowupItem, type FollowupKind, type FollowupVersion, type Job, type VideoCard } from '../api'
import { KIND_ONE, KIND_TITLES, shortDate, STATUS_AFTER, STATUSES, statusClass } from '../followup'
import { DetachDialog, EventChip } from '../FollowupsPanel'
import { HelpLink } from '../HelpMarkdown'
import { fmtDate, fmtDuration, parseTs, plural } from '../util'

type Tab = 'estado' | 'videos' | 'historial'
const KINDS: FollowupKind[] = ['tarea', 'decision', 'duda']
// Estado en que deja un punto cada evento (igual que EVENT_STATUS en backend/app/followups.py)
export default function FollowupDetail({ jobs }: { jobs: Job[] }) {
  const { id } = useParams()
  const nav = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) || 'estado'
  const [f, setF] = useState<FD | null>(null)
  const [error, setError] = useState('')
  const [editName, setEditName] = useState<{ name: string; description: string } | null>(null)
  const [rebuilding, setRebuilding] = useState(false)

  const load = useCallback(() => {
    api.get<FD>(`/api/followups/${id}`).then(setF).catch((e) => setError(e.message))
  }, [id])
  useEffect(load, [load])

  // Recargar al terminar el trabajo que lo estaba actualizando
  const job = f?.job_id ? jobs.find((j) => j.id === f.job_id) : undefined
  const jobStatus = job?.status
  useEffect(() => {
    if (jobStatus && jobStatus !== 'queued' && jobStatus !== 'running') load()
  }, [jobStatus, load])

  const act = async (fn: () => Promise<unknown>) => {
    setError('')
    try {
      const r = await fn()
      if (r && typeof r === 'object' && 'items' in r) setF(r as FD)
      else load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (!f) return error ? <div className="error-box">{error}</div> : <p className="muted">Cargando…</p>
  const tabs: [Tab, string][] = [['estado', 'Estado'], ['videos', `Vídeos (${f.n_videos})`], ['historial', 'Historial']]

  return (
    <>
      <div className="spread" style={{ marginBottom: '0.75rem' }}>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="small"><Link to="/seguimientos">← Seguimientos</Link></div>
          {editName ? (
            <div className="row" style={{ marginTop: '0.35rem' }}>
              <input value={editName.name} onChange={(e) => setEditName({ ...editName, name: e.target.value })} style={{ maxWidth: 320 }} />
              <input placeholder="Descripción breve" value={editName.description} onChange={(e) => setEditName({ ...editName, description: e.target.value })} style={{ maxWidth: 420 }} />
              <button className="sm primary" disabled={!editName.name.trim()} onClick={() => act(async () => {
                const r = await api.put(`/api/followups/${f.id}`, editName)
                setEditName(null)
                return r
              })}>Guardar</button>
              <button className="sm" onClick={() => setEditName(null)}>Cancelar</button>
            </div>
          ) : (
            <h1 style={{ margin: '0.25rem 0', cursor: 'text' }} title="Clic para editar" onClick={() => setEditName({ name: f.name, description: f.description })}>
              {f.name} {f.status === 'archivado' && <span className="pill">archivado</span>} <HelpLink to="seguimientos" />
            </h1>
          )}
          <div className="muted small">
            {f.description}{f.description && ' · '}{plural(f.n_videos, 'vídeo', 'vídeos')}
            {f.last_date && ` · último del ${fmtDate(f.last_date)}`}
          </div>
        </div>
        <div className="row">
          <button onClick={() => act(() => api.post(`/api/followups/${f.id}/open-folder`))}>Abrir carpeta</button>
          <button disabled={f.busy || !f.videos.some((v) => v.applied)} onClick={() => setRebuilding(!rebuilding)}
            title="La IA vuelve a aplicar los vídeos desde el que elijas; lo que cambiaste tú se conserva">Rehacer el estado…</button>
          <button onClick={() => act(() => api.put(`/api/followups/${f.id}`, { status: f.status === 'abierto' ? 'archivado' : 'abierto' }))}
            title={f.status === 'abierto' ? 'Deja de aparecer al encolar y no admite vídeos nuevos; se puede reabrir' : ''}>
            {f.status === 'abierto' ? 'Archivar' : 'Reabrir'}
          </button>
          <button className="danger" onClick={async () => {
            if (!confirm(`¿Borrar el seguimiento «${f.name}»? Los vídeos no se tocan.`)) return
            const folder = !!f.folder && confirm(`¿Borrar también su carpeta?\n${f.folder}\n\nAceptar: borrarla · Cancelar: conservarla`)
            await api.del(`/api/followups/${f.id}?delete_folder=${folder}`)
            nav('/seguimientos')
          }}>Borrar</button>
        </div>
      </div>

      {error && <div className="error-box" style={{ marginBottom: '1rem' }}>{error}</div>}
      {f.busy && (
        <div className="notice small" style={{ marginBottom: '1rem' }}>
          Actualizándose: hay un trabajo en la <Link to="/cola">cola</Link> que va a cambiar este estado.
          {job?.status === 'running' && ` ${job.message}`}
        </div>
      )}
      {f.pending_videos.length > 0 && (
        <div className="notice small" style={{ marginBottom: '1rem' }}>
          El estado se actualizará con {f.pending_videos.length > 1 ? 'estos vídeos' : 'este vídeo'} cuando apliques su revisión:{' '}
          {f.pending_videos.map((v, i) => <span key={v.id}>{i > 0 && ', '}«<Link to={`/videos/${v.id}/revisar`}>{v.title}</Link>»</span>)}.
        </div>
      )}
      {f.stale_from && !f.busy && (
        <div className="notice inline small warn-box" style={{ marginBottom: '1rem' }}>
          <span><b>El estado no está al día</b> desde el {fmtDate(f.stale_from)}. {f.stale_reason}</span>
          <button className="sm primary" onClick={() => act(() => api.post(`/api/followups/${f.id}/rebuild`))}>
            Rehacer el estado{f.rebuild_seconds ? ` (≈ ${fmtDuration(Math.max(f.rebuild_seconds, 30))})` : ''}
          </button>
        </div>
      )}
      {rebuilding && !f.busy && <RebuildPanel f={f} act={act} onClose={() => setRebuilding(false)} />}

      <div className="tabs">
        {tabs.map(([k, label]) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => { params.set('tab', k); setParams(params, { replace: true }) }}>{label}</button>
        ))}
      </div>
      {tab === 'estado' && <StateTab f={f} act={act} />}
      {tab === 'videos' && <VideosTab f={f} act={act} onChange={load} />}
      {tab === 'historial' && <HistoryTab f={f} onRestored={setF} />}
    </>
  )
}

type Act = (fn: () => Promise<unknown>) => Promise<void>

// Rehacer el estado desde un vídeo elegido (no hace falta que esté desactualizado)
function RebuildPanel({ f, act, onClose }: { f: FD; act: Act; onClose: () => void }) {
  const videos = f.videos.filter((v) => v.review !== 'pendiente')
  const [from, setFrom] = useState(String(videos[0]?.video_id ?? ''))
  const chosen = videos.find((v) => String(v.video_id) === from)
  return (
    <div className="notice inline small" style={{ marginBottom: '1rem' }}>
      <span>
        Rehacer el estado desde{' '}
        <select value={from} onChange={(e) => setFrom(e.target.value)} style={{ width: 'auto' }}>
          {videos.map((v) => <option key={v.video_id} value={v.video_id}>{fmtDate(v.date)} · {v.title}</option>)}
        </select>
        . La IA quita lo que aportaron ese vídeo y los siguientes y los vuelve a aplicar. Lo que cambiaste o borraste tú
        se conserva.
      </span>
      <span className="row" style={{ gap: '0.35rem' }}>
        <button className="sm" onClick={onClose}>Cancelar</button>
        <button className="sm primary" disabled={!chosen} onClick={() => act(async () => {
          const r = await api.post(`/api/followups/${f.id}/rebuild?since_video_id=${from}`)
          onClose()
          return r
        })}>Rehacer{chosen ? ` (≈ ${fmtDuration(Math.max(chosen.rebuild_seconds, 30))})` : ''}</button>
      </span>
    </div>
  )
}

// Texto con marcas «[AAAA-MM-DD hh:mm:ss]» que enlazan al vídeo de esa fecha en ese momento
function MomentText({ text, f }: { text: string; f: FD }) {
  const parts = text.split(/(\[\d{4}-\d{2}-\d{2}[ T·]+\d{1,2}:\d{2}:\d{2}\])/)
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[(\d{4}-\d{2}-\d{2})[ T·]+(\d{1,2}:\d{2}:\d{2})\]$/)
        if (!m) return <span key={i}>{p}</span>
        const v = f.videos.find((x) => x.date.slice(0, 10) === m[1])
        const label = `${shortDate(m[1])} · ${m[2]}`
        return v ? <Link key={i} to={`/videos/${v.video_id}?t=${parseTs(m[2]) ?? 0}&tab=resumen`} title={v.title}>{label}</Link>
          : <span key={i}>{label}</span>
      })}
    </>
  )
}

function SummaryCard({ f, act }: { f: FD; act: Act }) {
  const [editing, setEditing] = useState<string | null>(null)
  const [showAi, setShowAi] = useState(false)
  return (
    <div className="card pad">
      <div className="spread">
        <h3 style={{ margin: 0 }}>Resumen de la evolución {f.summary_manual && <span className="pill">editado por ti</span>}</h3>
        {editing === null && <button className="sm" onClick={() => setEditing(f.summary)}>Editar</button>}
      </div>
      {editing !== null ? (
        <div className="stack" style={{ marginTop: '0.5rem' }}>
          <textarea rows={6} value={editing} onChange={(e) => setEditing(e.target.value)} />
          <small className="muted">Si lo editas, la IA ya no lo reescribe: cuando tenga uno nuevo te lo ofrecerá. Déjalo vacío para volver al de la IA.</small>
          <div className="row">
            <button className="sm primary" onClick={() => act(async () => {
              const r = await api.put(`/api/followups/${f.id}`, { summary: editing })
              setEditing(null)
              return r
            })}>Guardar</button>
            <button className="sm" onClick={() => setEditing(null)}>Cancelar</button>
          </div>
        </div>
      ) : (
        <p style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>{f.summary ? <MomentText text={f.summary} f={f} /> : <span className="muted">Aún no hay resumen: se escribe al aplicar el primer vídeo.</span>}</p>
      )}
      {f.summary_ai && (
        <div className="notice small" style={{ marginTop: '0.75rem' }}>
          <div className="spread">
            <span>Hay un resumen nuevo de la IA.</span>
            <span className="row" style={{ gap: '0.35rem' }}>
              <button className="sm" onClick={() => setShowAi(!showAi)}>{showAi ? 'Ocultar' : 'Ver'}</button>
              <button className="sm primary" onClick={() => act(() => api.put(`/api/followups/${f.id}`, { use_ai_summary: true }))}>Usar el de la IA</button>
            </span>
          </div>
          {showAi && <p style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}><MomentText text={f.summary_ai} f={f} /></p>}
        </div>
      )}
    </div>
  )
}

function StateTab({ f, act }: { f: FD; act: Act }) {
  return (
    <div className="stack">
      <SummaryCard f={f} act={act} />
      {KINDS.map((k) => <ItemsCard key={k} f={f} kind={k} act={act} />)}
    </div>
  )
}

function ItemsCard({ f, kind, act }: { f: FD; kind: FollowupKind; act: Act }) {
  const [all, setAll] = useState(false)
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState({ text: '', owner: '', due: '' })
  const items = f.items.filter((it) => it.kind === kind)
  const open = items.filter((it) => it.status === STATUSES[kind][0])
  const shown = all ? items : open
  return (
    <div className="card pad">
      <div className="spread">
        <h3 style={{ margin: 0 }}>{KIND_TITLES[kind]} <span className="muted small">{open.length} {kind === 'decision' ? 'vigentes' : 'abiertas'} de {items.length}</span></h3>
        <span className="row" style={{ gap: '0.35rem' }}>
          {items.length > open.length && (
            <button className="sm" onClick={() => setAll(!all)}>{all ? `Solo ${kind === 'decision' ? 'vigentes' : 'abiertas'}` : 'Ver todas'}</button>
          )}
          <button className="sm" onClick={() => setAdding(!adding)}>+ Añadir a mano</button>
        </span>
      </div>
      {adding && (
        <div className="row" style={{ marginTop: '0.5rem', flexWrap: 'nowrap' }}>
          <input autoFocus placeholder={`Nueva ${KIND_ONE[kind]}`} value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
          {kind === 'tarea' && <input placeholder="Responsable" value={draft.owner} onChange={(e) => setDraft({ ...draft, owner: e.target.value })} style={{ maxWidth: 160 }} />}
          {kind === 'tarea' && <input placeholder="Plazo" value={draft.due} onChange={(e) => setDraft({ ...draft, due: e.target.value })} style={{ maxWidth: 120 }} />}
          <button className="sm primary" disabled={!draft.text.trim()} onClick={() => act(async () => {
            const r = await api.post(`/api/followups/${f.id}/items`, { kind, ...draft })
            setDraft({ text: '', owner: '', due: '' })
            setAdding(false)
            return r
          })}>Añadir</button>
        </div>
      )}
      {shown.length === 0 ? <p className="small muted" style={{ marginBottom: 0 }}>{items.length ? 'Nada abierto.' : 'Ninguna todavía.'}</p> : (
        <ul className="followup-items">
          {shown.map((it) => <ItemRow key={it.id} f={f} it={it} act={act} />)}
        </ul>
      )}
    </div>
  )
}

function ItemRow({ f, it, act }: { f: FD; it: FollowupItem; act: Act }) {
  const [edit, setEdit] = useState<{ text: string; owner: string; due: string } | null>(null)
  const url = `/api/followups/${f.id}/items/${it.id}`
  const lastPossible = it.events.map((e) => !!e.posible).lastIndexOf(true)
  return (
    <li>
      <div className="followup-item">
        <select value={it.status} className={`status-select ${statusClass(it.kind, it.status)}`} title="Cambiar el estado (queda como cambio tuyo)"
          onChange={(e) => act(() => api.put(url, { status: e.target.value }))}>
          {STATUSES[it.kind].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        {edit ? (
          <span className="row grow" style={{ flexWrap: 'nowrap' }}>
            <input value={edit.text} onChange={(e) => setEdit({ ...edit, text: e.target.value })} />
            {it.kind === 'tarea' && <input placeholder="Responsable" value={edit.owner} onChange={(e) => setEdit({ ...edit, owner: e.target.value })} style={{ maxWidth: 160 }} />}
            {it.kind === 'tarea' && <input placeholder="Plazo" value={edit.due} onChange={(e) => setEdit({ ...edit, due: e.target.value })} style={{ maxWidth: 120 }} />}
            <button className="sm primary" disabled={!edit.text.trim()} onClick={() => act(async () => {
              const r = await api.put(url, edit)
              setEdit(null)
              return r
            })}>Guardar</button>
            <button className="sm" onClick={() => setEdit(null)}>Cancelar</button>
          </span>
        ) : (
          <span className="grow">
            {it.text}
            {it.owner && <span className="muted"> — {it.owner}</span>}
            {it.due && <span className="muted"> (plazo: {it.due})</span>}
            {it.manual && <> <span className="pill" title="Lo has creado o cambiado tú: la IA ya no cambia su texto ni su estado">tuyo</span></>}
            {it.review?.tipo === 'duplicado' && (
              <div className="small warn-box" style={{ padding: '0.3rem 0.5rem', marginTop: '0.3rem' }}>
                ¿Es lo mismo que «{f.items.find((x) => x.id === it.review.de)?.text ?? it.review.texto ?? 'otro punto'}»?
                {it.review.motivo && <span className="muted"> {it.review.motivo}</span>}{' '}
                <button className="sm" onClick={() => act(() => api.post(`${url}/resolve`, { action: 'mismo' }))}>Sí, borrar este</button>{' '}
                <button className="sm" onClick={() => act(() => api.post(`${url}/resolve`, { action: 'distinto' }))}>No, es distinto</button>
              </div>
            )}
          </span>
        )}
        {!edit && (
          <span className="actions">
            <button className="sm" onClick={() => setEdit({ text: it.text, owner: it.owner, due: it.due })}>Editar</button>
            <button className="sm danger" onClick={() => confirm('¿Borrar este punto? La IA no lo volverá a crear.') && act(() => api.del(url))}>Borrar</button>
          </span>
        )}
      </div>
      <div className="events">
        {it.events.map((e, i) => (
          <EventChip key={i} e={e}
            onConfirm={e.posible && !e.descartado && i === lastPossible && it.status !== STATUS_AFTER[e.posible]
              ? () => act(() => api.put(url, { status: STATUS_AFTER[e.posible!] })) : undefined}
            onDismiss={e.posible && !e.descartado && i === lastPossible && it.status !== STATUS_AFTER[e.posible]
              ? () => act(() => api.post(`${url}/resolve`, { action: 'descartar' })) : undefined} />
        ))}
      </div>
    </li>
  )
}

function VideosTab({ f, act, onChange }: { f: FD; act: Act; onChange: () => void }) {
  const [detaching, setDetaching] = useState<{ id: number; title: string } | null>(null)
  const [library, setLibrary] = useState<VideoCard[]>([])
  const [adding, setAdding] = useState('')
  useEffect(() => { api.get<VideoCard[]>('/api/videos').then((vs) => setLibrary(vs.filter((v) => v.status === 'done'))) }, [])
  const inside = new Set(f.videos.map((v) => v.video_id))
  const candidates = library.filter((v) => !inside.has(v.id))
  return (
    <div className="stack">
      {f.videos.length === 0 && <div className="card pad muted">Sin vídeos. Añade uno aquí, desde la página del vídeo o al encolarlo.</div>}
      {f.videos.map((v) => (
        <div key={v.video_id} className="card pad">
          <div className="spread">
            <div>
              <b>{fmtDate(v.date)}</b> · <Link to={`/videos/${v.video_id}`}>{v.title}</Link>
              <span className="muted small"> · {fmtDuration(v.duration)}</span>
              {!v.applied && <> <span className="pill warn" title="El estado aún no incluye lo que dice este vídeo">sin aplicar</span></>}
            </div>
            <button className="sm" onClick={() => setDetaching({ id: v.video_id, title: v.title })}>Quitar del seguimiento</button>
          </div>
          {v.contribution && <p className="small" style={{ marginBottom: 0 }}>{v.contribution}</p>}
        </div>
      ))}
      {f.status === 'abierto' && candidates.length > 0 && (
        <div className="row">
          <select value={adding} onChange={(e) => setAdding(e.target.value)} style={{ maxWidth: 420 }}>
            <option value="">Añadir un vídeo ya analizado…</option>
            {candidates.map((v) => <option key={v.id} value={v.id}>{fmtDate(v.recorded_at ?? v.created_at)} · {v.title}</option>)}
          </select>
          <button className="sm primary" disabled={!adding} title="Lo añade y la IA rehace el estado desde su fecha"
            onClick={() => act(async () => {
              const r = await api.post(`/api/followups/${f.id}/videos/${adding}`, { apply: true })
              setAdding('')
              return r
            })}>Añadir y aplicar</button>
        </div>
      )}
      {detaching && <DetachDialog followupId={f.id} followupName={f.name} video={detaching}
        onClose={() => setDetaching(null)} onDone={() => { setDetaching(null); onChange() }} />}
    </div>
  )
}

function HistoryTab({ f, onRestored }: { f: FD; onRestored: (f: FD) => void }) {
  const [rows, setRows] = useState<FollowupVersion[] | null>(null)
  useEffect(() => { api.get<FollowupVersion[]>(`/api/followups/${f.id}/versions`).then(setRows) }, [f])
  if (!rows) return <p className="muted">Cargando…</p>
  return (
    <div className="card pad">
      <p className="small muted" style={{ marginTop: 0 }}>Cada cambio guarda antes una copia del estado. Restaurar una versión también guarda la actual.</p>
      <table className="tbl small">
        <thead><tr><th>Fecha</th><th>Motivo</th><th>Puntos</th><th>Vídeos aplicados</th><th /></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{fmtDate(r.created_at)}</td><td>{r.reason}</td><td>{r.items}</td><td>{r.videos}</td>
              <td><button className="sm" onClick={async () => {
                if (confirm('¿Volver a esta versión?')) onRestored(await api.post<FD>(`/api/followups/${f.id}/versions/${r.id}/restore`))
              }}>Restaurar</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

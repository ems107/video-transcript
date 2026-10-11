import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, type Job, type Person, type Proposals, type SpeakerInfo, type VideoDetail as VD } from '../api'
import { fmtDate, fmtDuration, fmtTs, parseTs, speakerColor, notifyKnowledge } from '../util'
import { JobRow } from './Queue'
import { CorrectionsPanel } from '../CorrectionsPanel'
import { RegenerateDialog } from '../RegenerateDialog'
import { RemoveDialog } from '../RemoveDialog'

type Tab = 'resumen' | 'transcripcion' | 'tareas' | 'pantalla'

// Convierte las marcas [hh:mm:ss] del texto en enlaces que saltan a ese momento del vídeo
function linkTimestamps(md: string): string {
  return md.replace(/\[?(\d{1,2}:\d{2}:\d{2})\]?(?!\()/g, (_, ts) => `[${ts}](#t=${parseTs(ts)})`)
}

function Markdown({ text, seek }: { text: string; seek: (t: number) => void }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) =>
            href?.startsWith('#t=') ? (
              <span className="ts-link" onClick={() => seek(Number(href.slice(3)))}>{children}</span>
            ) : (
              <a href={href} target="_blank" rel="noreferrer">{children}</a>
            ),
        }}
      >
        {linkTimestamps(text)}
      </ReactMarkdown>
    </div>
  )
}

function TsLink({ ts, seek }: { ts: string; seek: (t: number) => void }) {
  const t = parseTs(ts)
  if (t === null) return <span className="muted">{ts}</span>
  return <span className="ts-link" onClick={() => seek(t)}>{ts}</span>
}

function SpeakerPanel({ video, people, onChange }: { video: VD; people: Person[]; onChange: () => void }) {
  const [editing, setEditing] = useState<number | null>(null)
  const [newName, setNewName] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = video.speakers.filter((s) => !s.confirmed && (s.suggested_person_id || s.suggested_name)).length

  async function assign(sp: SpeakerInfo, body: object) {
    setBusy(true)
    try {
      await api.put(`/api/speakers/${sp.id}`, body)
      setEditing(null)
      setNewName('')
      notifyKnowledge()
      onChange()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card pad" style={{ marginTop: '1rem' }}>
      <div className="spread">
        <h3 style={{ margin: 0 }}>Hablantes</h3>
        {pending > 0 && (
          <button className="sm primary" disabled={busy} onClick={async () => {
            setBusy(true)
            await api.post(`/api/videos/${video.id}/confirm-speakers`)
            setBusy(false)
            notifyKnowledge()
            onChange()
          }}>Aceptar propuestas ({pending})</button>
        )}
      </div>
      {video.speakers.map((sp) => (
        <div key={sp.id} className="speaker-row">
          <div>
            <span className="dot" style={{ background: speakerColor(sp.order) }} />
            <b>{sp.name}</b>
            <span className="muted small"> · {fmtDuration(sp.speaking_time)}</span>
            <div className="small muted">
              {sp.confirmed ? (
                <span className="pill ok">Confirmado</span>
              ) : sp.suggested_person_id || sp.suggested_name ? (
                <span className="pill warn" title={sp.reason || undefined}>
                  Propuesta por {sp.source} ({Math.round(sp.confidence * 100)}%){sp.suggested_name && !sp.suggested_person_id ? ' · persona nueva' : ''}
                </span>
              ) : (
                <span className="pill">Sin identificar</span>
              )}
              {sp.is_owner && <span className="pill" style={{ marginLeft: 4 }}>tu micrófono</span>}
              {!sp.confirmed && sp.reason && <div>{sp.reason}</div>}
              {sp.aliases.length > 0 && <div>También le llaman {sp.aliases.map((a) => `«${a}»`).join(', ')}</div>}
            </div>
            {editing === sp.id && (
              <div className="row" style={{ marginTop: '0.5rem' }}>
                <select defaultValue="" disabled={busy} onChange={(e) => e.target.value && assign(sp, { person_id: Number(e.target.value) })}>
                  <option value="">Elegir persona…</option>
                  {people.map((p) => <option key={p.id} value={p.id}>{p.name}{p.role ? ` (${p.role})` : ''}</option>)}
                </select>
                <div className="row" style={{ flexWrap: 'nowrap', width: '100%' }}>
                  <input placeholder="…o nombre de una persona nueva" value={newName} onChange={(e) => setNewName(e.target.value)} />
                  <button className="sm" disabled={!newName.trim() || busy} onClick={() => assign(sp, { new_person_name: newName })}>Crear</button>
                </div>
              </div>
            )}
          </div>
          <div className="row" style={{ gap: '0.35rem' }}>
            {!sp.confirmed && (sp.suggested_person_id || sp.suggested_name) && (
              <button className="sm" disabled={busy} onClick={() => assign(sp, sp.suggested_person_id ? { person_id: sp.suggested_person_id } : { new_person_name: sp.suggested_name })}>
                Confirmar
              </button>
            )}
            <button className="sm" onClick={() => setEditing(editing === sp.id ? null : sp.id)}>{editing === sp.id ? 'Cerrar' : 'Cambiar'}</button>
          </div>
        </div>
      ))}
      <p className="small muted" style={{ marginBottom: 0 }}>
        Al confirmar, se guarda la huella de voz para reconocer a esa persona en próximos vídeos.
      </p>
    </div>
  )
}

// Lo aprendido de este vídeo: propuestas pendientes y acciones para crear o mejorar el perfil
function KnowledgePanel({ video, running, onChange }: { video: VD; running: boolean; onChange: () => void }) {
  const [counts, setCounts] = useState<{ ready: number; waiting: number } | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(() => {
    api.get<Proposals>(`/api/proposals?video_id=${video.id}`)
      .then((r) => setCounts({ ready: r.items.length, waiting: r.waiting.length }))
  }, [video.id])
  useEffect(load, [load, video])
  useEffect(() => {
    window.addEventListener('knowledge-changed', load)
    return () => window.removeEventListener('knowledge-changed', load)
  }, [load])

  async function run(fn: () => Promise<unknown>) {
    setError('')
    try {
      await fn()
      notifyKnowledge()
      onChange()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (video.status !== 'done') return null
  return (
    <div className="card pad" style={{ marginTop: '1rem' }}>
      <h3 style={{ marginTop: 0 }}>Aprendido de este vídeo</h3>
      {counts && (
        <p className="small" style={{ marginTop: 0 }}>
          {counts.ready > 0
            ? <Link to={`/propuestas?video=${video.id}`}><b>{counts.ready} propuestas</b> para revisar →</Link>
            : <span className="muted">No hay propuestas pendientes.</span>}
          {counts.waiting > 0 && <span className="muted"> · {counts.waiting} esperan a que confirmes hablantes</span>}
        </p>
      )}
      <div className="row" style={{ gap: '0.35rem' }}>
        {!video.profile_id && (
          <button className="sm primary" disabled={running} title="Crea un perfil nuevo para este tipo de vídeo y la IA propone su contenido" onClick={() => {
            const name = prompt('Nombre del nuevo perfil (p. ej. «Reuniones de equipo»):')
            if (name?.trim()) run(() => api.post('/api/profiles/from-video', { video_id: video.id, name }))
          }}>Crear perfil a partir de este vídeo</button>
        )}
        <button className="sm" disabled={running} title="La IA vuelve a leer el vídeo y propone lo que aprenda (lo rechazado no se repite)"
          onClick={() => run(() => api.post(`/api/videos/${video.id}/learn`))}>Aprender de nuevo</button>
        <button className="sm" disabled={running} title="Retira lo aceptado que solo venía de este vídeo y descarta sus propuestas"
          onClick={() => {
            if (confirm('¿Olvidar lo aprendido de este vídeo? Lo que solo venía de él se retira (recuperable desde el historial) y sus propuestas se descartan.')) {
              run(() => api.post(`/api/knowledge/forget-video/${video.id}`))
            }
          }}>Olvidar lo aprendido</button>
      </div>
      {error && <div className="error-box small" style={{ marginTop: '0.5rem' }}>{error}</div>}
    </div>
  )
}

export default function VideoDetail({ jobs }: { jobs: Job[] }) {
  const { id } = useParams()
  const nav = useNavigate()
  const [removing, setRemoving] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [params, setParams] = useSearchParams()
  const [video, setVideo] = useState<VD | null>(null)
  const [people, setPeople] = useState<Person[]>([])
  const [error, setError] = useState('')
  const [tab, setTab] = useState<Tab>((params.get('tab') as Tab) || 'resumen')
  const [time, setTime] = useState(0)
  const [follow, setFollow] = useState(true)
  const [filter, setFilter] = useState('')
  const [editTitle, setEditTitle] = useState<string | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const currentRef = useRef<HTMLDivElement>(null)

  const load = useCallback(() => {
    api.get<VD>(`/api/videos/${id}`).then(setVideo).catch((e) => setError(e.message))
    api.get<Person[]>('/api/people').then(setPeople)
  }, [id])
  useEffect(load, [load])

  // Recargar cuando termine un trabajo de este vídeo
  const job = jobs.find((j) => String(j.video_id) === id)
  const jobStatus = job?.status
  useEffect(() => {
    if (jobStatus === 'done') load()
  }, [jobStatus, load])

  const seek = useCallback((t: number) => {
    const v = videoRef.current
    if (v) {
      v.currentTime = t
      v.play().catch(() => {})
    }
  }, [])

  // Salto inicial desde la búsqueda (?t=123)
  useEffect(() => {
    const t = params.get('t')
    if (t && video && videoRef.current) {
      const v = videoRef.current
      const go = () => { v.currentTime = Number(t) }
      if (v.readyState >= 1) go()
      else v.addEventListener('loadedmetadata', go, { once: true })
    }
  }, [params, video])

  const order = useMemo(() => Object.fromEntries((video?.speakers ?? []).map((s) => [s.label, s.order])), [video])
  const currentIdx = useMemo(() => {
    if (!video) return -1
    let idx = -1
    for (let i = 0; i < video.segments.length; i++) {
      if (video.segments[i].start <= time + 0.2) idx = i
      else break
    }
    return idx
  }, [video, time])

  useEffect(() => {
    if (follow && tab === 'transcripcion') currentRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [currentIdx, follow, tab])

  if (error) return <div className="error-box">{error}</div>
  if (!video) return <p className="muted">Cargando…</p>

  const a = video.analysis ?? {}
  const f = filter.trim().toLowerCase()
  const segments = f ? video.segments.filter((s) => s.text.toLowerCase().includes(f) || s.name.toLowerCase().includes(f)) : video.segments
  const running = job && (job.status === 'running' || job.status === 'queued')

  function changeTab(t: Tab) {
    setTab(t)
    params.set('tab', t)
    setParams(params, { replace: true })
  }

  async function saveTitle() {
    if (editTitle && editTitle.trim() && editTitle !== video!.title) {
      await api.put(`/api/videos/${video!.id}`, { title: editTitle })
      load()
    }
    setEditTitle(null)
  }

  return (
    <>
      <div className="spread" style={{ marginBottom: '0.75rem' }}>
        <div className="grow" style={{ minWidth: 0 }}>
          {editTitle === null ? (
            <h1 style={{ marginBottom: '0.25rem', cursor: 'text' }} title="Clic para editar" onClick={() => setEditTitle(video.title)}>{video.title}</h1>
          ) : (
            <input autoFocus value={editTitle} onChange={(e) => setEditTitle(e.target.value)} onBlur={saveTitle}
              onKeyDown={(e) => { if (e.key === 'Enter') saveTitle(); if (e.key === 'Escape') setEditTitle(null) }}
              style={{ fontSize: '1.3rem', fontWeight: 700, marginBottom: '0.25rem' }} />
          )}
          <div className="muted small">
            {fmtDate(video.recorded_at ?? video.created_at)} · {fmtDuration(video.duration)}{video.profile && ` · ${video.profile}`}
          </div>
        </div>
        <div className="row">
          {video.folder && <button onClick={() => api.post(`/api/videos/${video.id}/open-folder`)}>Abrir carpeta</button>}
          {video.status === 'done' && (
            <button onClick={() => setRegenerating(true)} disabled={!!running}>Regenerar análisis</button>
          )}
          <button className="danger" disabled={!!running} onClick={() => setRemoving(true)}>Quitar</button>
          {regenerating && <RegenerateDialog videoId={video.id} onClose={() => setRegenerating(false)}
            onQueued={() => { setRegenerating(false); load() }} />}
          {removing && <RemoveDialog videoId={video.id} onClose={() => setRemoving(false)} onRemoved={() => nav('/')} />}
        </div>
      </div>

      {running && job && <div style={{ marginBottom: '1rem' }}><JobRow job={job} /></div>}
      {job?.status === 'error' && <div style={{ marginBottom: '1rem' }}><JobRow job={job} /></div>}

      <div className="detail">
        <div className="player-col">
          {(video.video_path || video.source_path) && (
            <video ref={videoRef} src={`/api/videos/${video.id}/file`} controls preload="metadata"
              onTimeUpdate={(e) => setTime((e.target as HTMLVideoElement).currentTime)} />
          )}
          {video.folder && <div className="small muted" style={{ marginTop: '0.4rem', wordBreak: 'break-all' }}>{video.folder}</div>}
          {video.speakers.length > 0 && <SpeakerPanel video={video} people={people} onChange={load} />}
          <KnowledgePanel video={video} running={!!running} onChange={load} />
          {video.status === 'done' && (
            <CorrectionsPanel video={video} running={!!running} onChange={load} onRegenerate={() => setRegenerating(true)} />
          )}
        </div>

        <div className="card pad" style={{ minWidth: 0 }}>
          <div className="tabs">
            {([['resumen', 'Resumen'], ['transcripcion', 'Transcripción'], ['tareas', 'Tareas y decisiones'], ['pantalla', `Pantalla (${video.keyframes.length})`]] as [Tab, string][]).map(([k, label]) => (
              <button key={k} className={tab === k ? 'active' : ''} onClick={() => changeTab(k)}>{label}</button>
            ))}
          </div>

          {tab === 'resumen' && (
            <div>
              {!a.resumen_detallado && <p className="muted">Aún no hay resumen.</p>}
              {a.resumen_breve && <p><b>{a.resumen_breve}</b></p>}
              {a.resumen_detallado && <Markdown text={a.resumen_detallado} seek={seek} />}
              {a.participantes && a.participantes.length > 0 && (
                <>
                  <h3>Participantes</h3>
                  <ul>{a.participantes.map((p) => <li key={p.nombre}><b>{p.nombre}</b>{p.papel && ` — ${p.papel}`}</li>)}</ul>
                </>
              )}
              {a.temas && a.temas.length > 0 && (
                <div className="row small" style={{ gap: '0.35rem' }}>{a.temas.map((t) => <span key={t} className="pill">{t}</span>)}</div>
              )}
            </div>
          )}

          {tab === 'transcripcion' && (
            <>
              <div className="row" style={{ marginBottom: '0.5rem', flexWrap: 'nowrap' }}>
                <input placeholder="Buscar en la transcripción…" value={filter} onChange={(e) => setFilter(e.target.value)} />
                <label className="check small" style={{ whiteSpace: 'nowrap' }}>
                  <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Seguir vídeo
                </label>
              </div>
              <div className="transcript">
                {segments.map((s) => {
                  const isCur = !f && video.segments[currentIdx]?.id === s.id
                  return (
                    <div key={s.id} ref={isCur ? currentRef : undefined} className={`utt ${isCur ? 'current' : ''}`} onClick={() => seek(s.start)}>
                      <span className="ts">{fmtTs(s.start)}</span>
                      <div>
                        <div className="who" style={{ color: speakerColor(order[s.speaker] ?? 1) }}>{s.name}</div>
                        <div className={s.corrections.length ? 'corr' : ''}
                          title={s.corrections.length ? `Corregido según el glosario:\n${s.corrections.map((c) => `«${c.original}» → «${c.suggestion}»`).join('\n')}` : undefined}>
                          {s.text}
                        </div>
                      </div>
                    </div>
                  )
                })}
                {segments.length === 0 && <p className="muted">Sin resultados.</p>}
              </div>
            </>
          )}

          {tab === 'tareas' && (
            <div>
              <h3 style={{ marginTop: 0 }}>Tareas</h3>
              {a.tareas?.length ? (
                <table className="tbl">
                  <thead><tr><th>Responsable</th><th>Tarea</th><th>Plazo</th><th>Momento</th></tr></thead>
                  <tbody>
                    {a.tareas.map((t, i) => (
                      <tr key={i}><td>{t.responsable || '—'}</td><td>{t.tarea}</td><td>{t.plazo || '—'}</td><td><TsLink ts={t.t} seek={seek} /></td></tr>
                    ))}
                  </tbody>
                </table>
              ) : <p className="muted">No se detectaron tareas.</p>}
              <h3>Decisiones</h3>
              {a.decisiones?.length ? (
                <ul>{a.decisiones.map((d, i) => <li key={i}>{d.decision} <TsLink ts={d.t} seek={seek} /></li>)}</ul>
              ) : <p className="muted">No se detectaron decisiones.</p>}
              <h3>Pendientes</h3>
              {a.pendientes?.length ? <ul>{a.pendientes.map((p, i) => <li key={i}>{p}</li>)}</ul> : <p className="muted">Nada pendiente.</p>}
            </div>
          )}

          {tab === 'pantalla' && (
            <div className="frames">
              {video.keyframes.map((k) => (
                <figure key={k.id} onClick={() => seek(k.t)} title={k.visible_text}>
                  <img src={`/api/keyframes/${k.id}/image`} alt="" loading="lazy" />
                  <figcaption><b>{fmtTs(k.t)}</b> · {k.scene_type}{k.active_speaker && ` · habla ${k.active_speaker}`}<br />{k.description}</figcaption>
                </figure>
              ))}
              {video.keyframes.length === 0 && <p className="muted">No se analizó la imagen de este vídeo.</p>}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

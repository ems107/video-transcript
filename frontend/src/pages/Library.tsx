import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type Person, type Profile, type VideoCard } from '../api'
import { fmtDate, fmtDuration, STATUS_LABEL } from '../util'
import { HelpLink } from '../HelpMarkdown'

export default function Library() {
  const [videos, setVideos] = useState<VideoCard[] | null>(null)
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [people, setPeople] = useState<Person[]>([])
  const [profileId, setProfileId] = useState('')
  const [params] = useSearchParams()
  const [personId, setPersonId] = useState(params.get('person') ?? '')
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<Profile[]>('/api/profiles').then(setProfiles)
    api.get<Person[]>('/api/people').then(setPeople)
  }, [])

  useEffect(() => {
    const qs = new URLSearchParams()
    if (profileId) qs.set('profile_id', profileId)
    if (personId) qs.set('person_id', personId)
    api.get<VideoCard[]>(`/api/videos?${qs}`).then(setVideos).catch((e) => setError(e.message))
  }, [profileId, personId])

  const shown = useMemo(() => {
    const f = filter.trim().toLowerCase()
    return (videos ?? []).filter((v) => !f || v.title.toLowerCase().includes(f) || v.summary.toLowerCase().includes(f))
  }, [videos, filter])

  return (
    <>
      <div className="spread" style={{ marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Biblioteca <HelpLink to="primeros-pasos" /></h1>
        <Link to="/nuevo"><button className="primary">+ Analizar vídeo</button></Link>
      </div>
      <div className="row" style={{ marginBottom: '1rem' }}>
        <input style={{ maxWidth: 320 }} placeholder="Filtrar por título o resumen…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <select style={{ maxWidth: 220 }} value={profileId} onChange={(e) => setProfileId(e.target.value)}>
          <option value="">Todos los perfiles</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select style={{ maxWidth: 220 }} value={personId} onChange={(e) => setPersonId(e.target.value)}>
          <option value="">Todas las personas</option>
          {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
      {error && <div className="error-box">{error}</div>}
      {videos && shown.length === 0 && (
        <div className="card pad muted">
          {videos.length === 0 ? <>Aún no hay vídeos analizados. <Link to="/nuevo">Analiza el primero</Link>.</> : 'Ningún vídeo coincide con el filtro.'}
        </div>
      )}
      <div className="video-grid">
        {shown.map((v) => (
          <Link key={v.id} to={`/videos/${v.id}`} className="card video-card">
            <div className="thumb">
              {v.has_thumbnail ? <img src={`/api/videos/${v.id}/thumbnail`} alt="" loading="lazy" /> : <span>{STATUS_LABEL[v.status] ?? v.status}</span>}
              {v.duration > 0 && <span className="dur">{fmtDuration(v.duration)}</span>}
            </div>
            <div className="body">
              <div className="title">{v.title}</div>
              <div className="muted small">{fmtDate(v.recorded_at ?? v.created_at)}{v.profile && ` · ${v.profile}`}</div>
              {v.summary && <p className="small clamp" style={{ margin: '0.5rem 0' }}>{v.summary}</p>}
              <div className="row small" style={{ gap: '0.35rem' }}>
                {v.status !== 'done' && <span className={`pill ${v.status === 'error' ? 'err' : 'run'}`}>{STATUS_LABEL[v.status] ?? v.status}</span>}
                {v.pending_speakers > 0 && v.status === 'done' && <span className="pill warn">{v.pending_speakers} hablante(s) por confirmar</span>}
                {v.people.slice(0, 5).map((p) => <span key={p} className="pill">{p}</span>)}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </>
  )
}

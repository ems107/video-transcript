import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type Person, type Profile, type SearchHit } from '../api'
import { fmtTs } from '../util'
import { HelpLink } from '../HelpMarkdown'

const KIND: Record<string, string> = { segment: 'Transcripción', summary: 'Resumen', title: 'Título', frame: 'Pantalla' }

function Snippet({ text }: { text: string }) {
  const parts = text.split(/\[\[|\]\]/)
  return <>{parts.map((p, i) => (i % 2 ? <mark key={i}>{p}</mark> : <span key={i}>{p}</span>))}</>
}

export default function Search() {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const [profileId, setProfileId] = useState('')
  const [personId, setPersonId] = useState('')
  const [hits, setHits] = useState<SearchHit[] | null>(null)
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [people, setPeople] = useState<Person[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<Profile[]>('/api/profiles').then(setProfiles)
    api.get<Person[]>('/api/people').then(setPeople)
  }, [])

  useEffect(() => {
    const query = params.get('q') ?? ''
    if (query.trim().length < 2) {
      setHits(null)
      return
    }
    const qs = new URLSearchParams({ q: query })
    if (profileId) qs.set('profile_id', profileId)
    if (personId) qs.set('person_id', personId)
    setError('')
    api.get<SearchHit[]>(`/api/search?${qs}`).then(setHits).catch((e) => setError(e.message))
  }, [params, profileId, personId])

  const grouped = new Map<number, SearchHit[]>()
  for (const h of hits ?? []) grouped.set(h.video_id, [...(grouped.get(h.video_id) ?? []), h])

  return (
    <>
      <h1>Buscar en todos los vídeos <HelpLink to="buscar" /></h1>
      <div className="row" style={{ marginBottom: '1rem' }}>
        <input style={{ maxWidth: 420 }} autoFocus placeholder='Palabras o "frase exacta"…' value={q}
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && setParams({ q })} />
        <button className="primary" onClick={() => setParams({ q })}>Buscar</button>
        <select style={{ maxWidth: 200 }} value={profileId} onChange={(e) => setProfileId(e.target.value)}>
          <option value="">Todos los perfiles</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select style={{ maxWidth: 200 }} value={personId} onChange={(e) => setPersonId(e.target.value)}>
          <option value="">Cualquier persona</option>
          {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
      {error && <div className="error-box">{error}</div>}
      {hits && hits.length === 0 && <p className="muted">Sin resultados.</p>}
      <div className="stack">
        {[...grouped.entries()].map(([vid, hs]) => (
          <div key={vid} className="card pad">
            <Link to={`/videos/${vid}`}><b>{hs[0].video_title}</b></Link>
            {hs.map((h, i) => (
              <div key={i} className="hit small">
                <span className="pill">{KIND[h.kind]}</span>{' '}
                {(h.kind === 'segment' || h.kind === 'frame') && (
                  <Link to={`/videos/${vid}?t=${Math.floor(h.t)}&tab=${h.kind === 'frame' ? 'pantalla' : 'transcripcion'}`}>{fmtTs(h.t)}</Link>
                )}
                {h.speaker && <b> {h.speaker}:</b>} <Snippet text={h.snippet} />
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  )
}

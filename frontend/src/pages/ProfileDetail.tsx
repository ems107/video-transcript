import { useCallback, useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, type Person, type Profile } from '../api'
import { KnowledgeList, ProposalList, VersionHistory } from '../knowledge'
import { plural } from '../util'
import { Editor } from './Profiles'

type Tab = 'manual' | 'aprendido' | 'propuestas' | 'historial'

export default function ProfileDetail() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) || 'manual'
  const [profile, setProfile] = useState<Profile | null>(null)
  const [people, setPeople] = useState<Person[]>([])
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.get<Profile>(`/api/profiles/${id}`).then(setProfile).catch((e) => setError(e.message))
    api.get<Person[]>('/api/people').then(setPeople)
  }, [id])
  useEffect(load, [load])

  if (error) return <div className="error-box">{error}</div>
  if (!profile) return <p className="muted">Cargando…</p>

  const tabs: [Tab, string][] = [
    ['manual', 'Manual'],
    ['aprendido', `Aprendido (${profile.learned_count})`],
    ['propuestas', `Propuestas${profile.pending_count ? ` (${profile.pending_count})` : ''}`],
    ['historial', 'Historial'],
  ]

  return (
    <>
      <div className="spread" style={{ marginBottom: '0.75rem' }}>
        <div>
          <div className="small"><Link to="/perfiles">← Perfiles</Link></div>
          <h1 style={{ margin: '0.25rem 0' }}>{profile.name}</h1>
          <div className="muted small">{profile.description}{profile.description && ' · '}{plural(profile.video_count, 'vídeo', 'vídeos')}</div>
        </div>
        <button title="La IA vuelve a leer los vídeos ya analizados de este perfil y propone lo que aprenda" onClick={async () => {
          const r = await api.post<{ queued: number; skipped: number }>(`/api/profiles/${profile.id}/learn-all`)
          setNotice(`${r.queued} vídeos en cola para aprender${r.skipped ? ` (${r.skipped} omitidos: en curso o sin datos intermedios)` : ''}. Las propuestas aparecerán al terminar.`)
        }}>Aprender de todos sus vídeos</button>
      </div>
      {notice && <div className="notice small" style={{ marginBottom: '1rem' }}>{notice}</div>}
      <div className="tabs">
        {tabs.map(([k, label]) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => { params.set('tab', k); setParams(params, { replace: true }) }}>{label}</button>
        ))}
      </div>
      {tab === 'manual' && (
        <Editor key={JSON.stringify(profile)} initial={profile} people={people} onSaved={() => { setNotice('Guardado.'); load() }} />
      )}
      {tab === 'aprendido' && (
        <>
          <p className="muted small">Lo aprendido de los vídeos y aceptado por ti. Se usa junto a lo manual; si se contradicen, prevalece lo manual.</p>
          <KnowledgeList url={`/api/profiles/${profile.id}/knowledge`} empty="Aún no hay nada aprendido. Acepta propuestas para que aparezcan aquí." />
        </>
      )}
      {tab === 'propuestas' && (
        <ProposalList query={`profile_id=${profile.id}`} showOwner={false} empty="No hay propuestas pendientes para este perfil." />
      )}
      {tab === 'historial' && (
        <VersionHistory base={`/api/profiles/${profile.id}`} onRestored={load} />
      )}
    </>
  )
}

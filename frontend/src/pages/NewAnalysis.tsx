import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Followup, type ProbeInfo, type Profile, type Settings } from '../api'
import { fmtDate, fmtDuration } from '../util'
import { HelpLink } from '../HelpMarkdown'

export default function NewAnalysis() {
  const nav = useNavigate()
  const [path, setPath] = useState('')
  const [info, setInfo] = useState<ProbeInfo | null>(null)
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [profileId, setProfileId] = useState('')
  const [followups, setFollowups] = useState<Followup[]>([])
  const [followupIds, setFollowupIds] = useState<number[]>([])
  const [mainTrack, setMainTrack] = useState('mix')
  const [ownerTrack, setOwnerTrack] = useState('')
  const [fileMode, setFileMode] = useState('')
  const [skipVision, setSkipVision] = useState(false)
  const [minSpk, setMinSpk] = useState('')
  const [maxSpk, setMaxSpk] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get<Profile[]>('/api/profiles').then((ps) => {
      setProfiles(ps)
      if (ps.length === 1) setProfileId(String(ps[0].id))
    })
    api.get<Settings>('/api/settings').then((s) => setFileMode(String(s.file_mode)))
    api.get<Followup[]>('/api/followups').then((fs) => setFollowups(fs.filter((f) => f.status === 'abierto')))
  }, [])

  async function check() {
    setError('')
    setInfo(null)
    try {
      const i = await api.get<ProbeInfo>(`/api/probe?path=${encodeURIComponent(path)}`)
      setInfo(i)
      setMainTrack(i.audio_tracks.length > 1 ? 'mix' : '0')
      setOwnerTrack('')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function submit() {
    setBusy(true)
    setError('')
    const options: Record<string, unknown> = { file_mode: fileMode, skip_vision: skipVision }
    if (mainTrack !== 'mix') options.main_track = Number(mainTrack)
    if (ownerTrack !== '') options.owner_track = Number(ownerTrack)
    if (minSpk) options.min_speakers = Number(minSpk)
    if (maxSpk) options.max_speakers = Number(maxSpk)
    try {
      await api.post('/api/jobs', { path: info?.path ?? path, profile_id: profileId ? Number(profileId) : null,
        followup_ids: followupIds, options })
      nav('/cola')
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  const tracks = info?.audio_tracks ?? []
  const trackName = (t: ProbeInfo['audio_tracks'][number]) => `Pista ${t.index + 1}${t.title ? ` · ${t.title}` : ''} (${t.channels} canal${t.channels === 1 ? '' : 'es'})`

  return (
    <>
      <h1>Nuevo análisis <HelpLink to="analizar" /></h1>
      <div className="card pad stack" style={{ maxWidth: 820 }}>
        <label className="field">
          <span>Ruta del vídeo</span>
          <div className="row" style={{ flexWrap: 'nowrap' }}>
            <input
              placeholder='C:\Users\…\Videos\grabacion.mp4  (en el Explorador: Mayús + clic derecho → "Copiar como ruta")'
              value={path}
              onChange={(e) => { setPath(e.target.value); setInfo(null) }}
              onKeyDown={(e) => e.key === 'Enter' && check()}
            />
            <button onClick={check} disabled={!path.trim()}>Comprobar</button>
          </div>
        </label>

        {error && <div className="error-box">{error}</div>}

        {info && (
          <>
            <div className="notice small">
              <b>{info.path.split(/[\\/]/).pop()}</b> · {fmtDuration(info.duration)} · {(info.size / 1e9).toFixed(2)} GB
              {info.width && ` · ${info.width}×${info.height}`} · {tracks.length} pista(s) de audio · grabado {fmtDate(info.recorded_at)}
            </div>

            <label className="field">
              <span>Perfil</span>
              <select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
                <option value="">Sin perfil</option>
                {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <small>Aporta contexto, glosario y personas para mejorar la transcripción y el análisis.</small>
            </label>

            {followups.length > 0 && (
              <div className="field">
                <span className="label">Seguimientos <HelpLink to="seguimientos" /></span>
                <div className="row" style={{ gap: '0.35rem 1rem' }}>
                  {followups.map((f) => (
                    <label key={f.id} className="check small">
                      <input type="checkbox" checked={followupIds.includes(f.id)} onChange={(e) => {
                        setFollowupIds(e.target.checked ? [...followupIds, f.id] : followupIds.filter((x) => x !== f.id))
                        // Lo normal es que los vídeos de un seguimiento usen el mismo perfil
                        if (e.target.checked && !profileId && f.profile_id) setProfileId(String(f.profile_id))
                      }} />
                      {f.name}
                    </label>
                  ))}
                </div>
                <small>Si el vídeo continúa uno de estos temas: el análisis tiene en cuenta lo anterior y el estado del seguimiento se actualiza al terminar.</small>
              </div>
            )}

            {tracks.length > 1 && (
              <div className="grid2">
                <label className="field">
                  <span>Audio para transcribir</span>
                  <select value={mainTrack} onChange={(e) => setMainTrack(e.target.value)}>
                    <option value="mix">Mezclar todas las pistas</option>
                    {tracks.map((t) => <option key={t.index} value={t.index}>{trackName(t)}</option>)}
                  </select>
                  <small>Si una pista ya contiene todo el audio (algunos grabadores guardan una pista con la mezcla completa), elígela.</small>
                </label>
                <label className="field">
                  <span>Pista de tu micrófono</span>
                  <select value={ownerTrack} onChange={(e) => setOwnerTrack(e.target.value)}>
                    <option value="">No hay / no lo sé</option>
                    {tracks.map((t) => <option key={t.index} value={t.index}>{trackName(t)}</option>)}
                  </select>
                  <small>Permite identificarte a ti automáticamente.</small>
                </label>
              </div>
            )}

            <div className="grid2">
              <label className="field">
                <span>Mínimo de hablantes</span>
                <input type="number" min={1} placeholder="Automático" value={minSpk} onChange={(e) => setMinSpk(e.target.value)} />
              </label>
              <label className="field">
                <span>Máximo de hablantes</span>
                <input type="number" min={1} placeholder="Automático" value={maxSpk} onChange={(e) => setMaxSpk(e.target.value)} />
              </label>
            </div>

            <label className="field">
              <span>Al terminar</span>
              <select value={fileMode} onChange={(e) => setFileMode(e.target.value)}>
                <option value="move">Mover el vídeo a su carpeta de resultados</option>
                <option value="copy">Copiar el vídeo (el original no se toca)</option>
              </select>
            </label>

            <label className="check">
              <input type="checkbox" checked={skipVision} onChange={(e) => setSkipVision(e.target.checked)} />
              No analizar la imagen (más rápido; solo audio)
            </label>

            <div>
              <button className="primary" onClick={submit} disabled={busy}>Añadir a la cola</button>
            </div>
          </>
        )}
      </div>
    </>
  )
}

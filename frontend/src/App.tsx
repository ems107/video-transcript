import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { api, type Status } from './api'
import { useJobs } from './util'
import Library from './pages/Library'
import NewAnalysis from './pages/NewAnalysis'
import Queue from './pages/Queue'
import VideoDetail from './pages/VideoDetail'
import Search from './pages/Search'
import Profiles from './pages/Profiles'
import People from './pages/People'
import SettingsPage from './pages/Settings'
import Proposals from './pages/Proposals'
import ProfileDetail from './pages/ProfileDetail'
import PersonDetail from './pages/PersonDetail'
import Help from './pages/Help'
import Followups from './pages/Followups'
import FollowupDetail from './pages/FollowupDetail'
import Review from './pages/Review'

const CHECK_LABELS: Record<string, string> = {
  ffmpeg: 'ffmpeg',
  llama_server: 'llama.cpp',
  llm_model: 'modelo Qwen3.6',
  llm_mmproj: 'visión de Qwen3.6',
  whisper: 'Whisper large-v3',
  align: 'alineamiento wav2vec2',
  diarization: 'pyannote community-1',
}

export default function App() {
  const jobs = useJobs()
  const active = jobs.filter((j) => j.status === 'queued' || j.status === 'running' || j.status === 'waiting').length
  const [status, setStatus] = useState<Status | null>(null)

  // El contador de propuestas cambia al terminar trabajos o al decidir propuestas
  const finished = jobs.filter((j) => j.status === 'done').length
  useEffect(() => {
    const load = () => { api.get<Status>('/api/status').then(setStatus).catch(() => setStatus(null)) }
    load()
    window.addEventListener('knowledge-changed', load)
    return () => window.removeEventListener('knowledge-changed', load)
  }, [finished])

  const missing = status ? Object.entries(status.checks).filter(([, ok]) => !ok).map(([k]) => CHECK_LABELS[k] ?? k) : []

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          Vídeo Transcript
          <small>Transcripción y análisis local</small>
        </div>
        <nav className="nav">
          <NavLink to="/" end>
            Biblioteca {!!status?.to_review && <span className="badge" title="Vídeos por revisar">{status.to_review}</span>}
          </NavLink>
          <NavLink to="/nuevo">Nuevo análisis</NavLink>
          <NavLink to="/cola">
            Cola {active > 0 && <span className="badge">{active}</span>}
          </NavLink>
          <NavLink to="/propuestas">
            Propuestas {!!status?.pending_proposals && <span className="badge">{status.pending_proposals}</span>}
          </NavLink>
          <NavLink to="/buscar">Buscar</NavLink>
          <NavLink to="/perfiles">Perfiles</NavLink>
          <NavLink to="/seguimientos">Seguimientos</NavLink>
          <NavLink to="/personas">Personas</NavLink>
          <NavLink to="/ajustes">Ajustes</NavLink>
          <NavLink to="/ayuda">Ayuda</NavLink>
        </nav>
        {status?.version && <div className="version">v{status.version}</div>}
      </aside>
      <main className="main">
        {missing.length > 0 && (
          <div className="error-box" style={{ marginBottom: '1rem' }}>
            Faltan componentes: {missing.join(', ')}. Ejecuta <code>scripts/download_models.py</code> (ver README).
          </div>
        )}
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/nuevo" element={<NewAnalysis />} />
          <Route path="/cola" element={<Queue jobs={jobs} />} />
          <Route path="/videos/:id" element={<VideoDetail jobs={jobs} />} />
          <Route path="/videos/:id/revisar" element={<Review jobs={jobs} />} />
          <Route path="/buscar" element={<Search />} />
          <Route path="/propuestas" element={<Proposals />} />
          <Route path="/perfiles" element={<Profiles />} />
          <Route path="/perfiles/:id" element={<ProfileDetail />} />
          <Route path="/seguimientos" element={<Followups />} />
          <Route path="/seguimientos/:id" element={<FollowupDetail jobs={jobs} />} />
          <Route path="/personas" element={<People />} />
          <Route path="/personas/:id" element={<PersonDetail />} />
          <Route path="/ajustes" element={<SettingsPage />} />
          <Route path="/ayuda" element={<Help />} />
          <Route path="/ayuda/:pagina" element={<Help />} />
        </Routes>
      </main>
    </div>
  )
}

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
  const active = jobs.filter((j) => j.status === 'queued' || j.status === 'running').length
  const [status, setStatus] = useState<Status | null>(null)

  useEffect(() => {
    api.get<Status>('/api/status').then(setStatus).catch(() => setStatus(null))
  }, [])

  const missing = status ? Object.entries(status.checks).filter(([, ok]) => !ok).map(([k]) => CHECK_LABELS[k] ?? k) : []

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          Vídeo Transcript
          <small>Transcripción y análisis local</small>
        </div>
        <nav className="nav">
          <NavLink to="/" end>Biblioteca</NavLink>
          <NavLink to="/nuevo">Nuevo análisis</NavLink>
          <NavLink to="/cola">
            Cola {active > 0 && <span className="badge">{active}</span>}
          </NavLink>
          <NavLink to="/buscar">Buscar</NavLink>
          <NavLink to="/perfiles">Perfiles</NavLink>
          <NavLink to="/personas">Personas</NavLink>
          <NavLink to="/ajustes">Ajustes</NavLink>
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
          <Route path="/buscar" element={<Search />} />
          <Route path="/perfiles" element={<Profiles />} />
          <Route path="/personas" element={<People />} />
          <Route path="/ajustes" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  )
}

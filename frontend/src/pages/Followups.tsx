import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type Followup, type FollowupDetail } from '../api'
import { HelpLink } from '../HelpMarkdown'
import { fmtDate, plural } from '../util'

export default function Followups() {
  const nav = useNavigate()
  const [rows, setRows] = useState<Followup[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { api.get<Followup[]>('/api/followups').then(setRows) }, [])

  async function create() {
    setError('')
    try {
      const f = await api.post<FollowupDetail>('/api/followups', { name, description })
      nav(`/seguimientos/${f.id}`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const open = (rows ?? []).filter((f) => f.status === 'abierto')
  const archived = (rows ?? []).filter((f) => f.status === 'archivado')

  return (
    <>
      <div className="spread" style={{ marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Seguimientos <HelpLink to="seguimientos" /></h1>
        {!creating && <button className="primary" onClick={() => setCreating(true)}>+ Nuevo seguimiento</button>}
      </div>
      {creating && (
        <div className="card pad stack" style={{ marginBottom: '1rem', maxWidth: 720 }}>
          <div className="grid2">
            <label className="field"><span>Nombre</span><input autoFocus value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label className="field"><span>Descripción breve (opcional)</span><input value={description} onChange={(e) => setDescription(e.target.value)} /></label>
          </div>
          <small className="muted">Después añade sus vídeos desde la página de cada vídeo o al encolarlos.</small>
          {error && <div className="error-box">{error}</div>}
          <div className="row">
            <button className="primary" disabled={!name.trim()} onClick={create}>Crear</button>
            <button onClick={() => setCreating(false)}>Cancelar</button>
          </div>
        </div>
      )}
      {!rows ? <p className="muted">Cargando…</p> : (
        <div className="stack">
          {rows.length === 0 && (
            <div className="card pad muted">
              Un seguimiento reúne los vídeos de un mismo tema (las sesiones de un curso, las reuniones de un proyecto…) y
              lleva su estado: qué se pidió, qué está hecho, qué se decidió y qué sigue pendiente, con el vídeo y el momento
              de cada cosa.
            </div>
          )}
          {open.map((f) => <Row key={f.id} f={f} />)}
          {archived.length > 0 && (
            <label className="check small"><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
              Mostrar los archivados ({archived.length})</label>
          )}
          {showArchived && archived.map((f) => <Row key={f.id} f={f} />)}
        </div>
      )}
    </>
  )
}

function Row({ f }: { f: Followup }) {
  return (
    <div className="card pad spread">
      <div>
        <Link to={`/seguimientos/${f.id}`}><b>{f.name}</b></Link> <span className="muted small">{f.description}</span>
        {f.status === 'archivado' && <> <span className="pill">archivado</span></>}
        <div className="muted small">
          {plural(f.n_videos, 'vídeo', 'vídeos')}{f.last_date && ` · último del ${fmtDate(f.last_date)}`}
          {' · '}{plural(f.open_tasks, 'tarea abierta', 'tareas abiertas')}
          {f.stale_from && <> · <span className="pill warn">desactualizado</span></>}
          {f.busy && <> · <span className="pill run">actualizándose</span></>}
        </div>
      </div>
      <Link to={`/seguimientos/${f.id}`}><button className="sm">Abrir</button></Link>
    </div>
  )
}

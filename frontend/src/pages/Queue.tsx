import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Job } from '../api'
import { fmtDate, STATUS_LABEL } from '../util'

const PILL: Record<string, string> = { running: 'run', done: 'ok', error: 'err', cancelled: '', queued: '' }

export function JobRow({ job }: { job: Job }) {
  const [showErr, setShowErr] = useState(false)
  const name = job.video_title || job.video_source.split(/[\\/]/).pop()
  return (
    <div className="card pad">
      <div className="spread">
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="row">
            <Link to={`/videos/${job.video_id}`}><b>{name}</b></Link>
            <span className={`pill ${PILL[job.status]}`}>{STATUS_LABEL[job.status]}</span>
          </div>
          <div className="muted small">
            {job.status === 'running' || job.status === 'queued' ? `${job.stage_label || 'Esperando'} — ${job.message}` : job.message}
            {job.finished_at && ` · ${fmtDate(job.finished_at)}`}
          </div>
        </div>
        <div className="row">
          {(job.status === 'running' || job.status === 'queued') && (
            <button className="sm danger" onClick={() => api.post(`/api/jobs/${job.id}/cancel`)}>Cancelar</button>
          )}
          {(job.status === 'error' || job.status === 'cancelled') && (
            <button className="sm" onClick={() => api.post(`/api/jobs/${job.id}/retry`)}>Reintentar</button>
          )}
          {job.error && <button className="sm" onClick={() => setShowErr(!showErr)}>Detalles</button>}
        </div>
      </div>
      {(job.status === 'running' || job.status === 'queued') && (
        <div className="row" style={{ marginTop: '0.5rem', flexWrap: 'nowrap' }}>
          <div className="progress grow"><div style={{ width: `${job.progress * 100}%` }} /></div>
          <span className="small muted" style={{ width: '3rem', textAlign: 'right' }}>{Math.round(job.progress * 100)}%</span>
        </div>
      )}
      {showErr && <pre className="error-box small" style={{ whiteSpace: 'pre-wrap', marginTop: '0.5rem' }}>{job.error}</pre>}
    </div>
  )
}

export default function Queue({ jobs }: { jobs: Job[] }) {
  return (
    <>
      <h1>Cola de procesamiento</h1>
      <p className="muted small">Los vídeos se procesan de uno en uno. Si cierras la aplicación, el trabajo se reanuda desde la última fase completada.</p>
      <div className="stack">
        {jobs.length === 0 && <div className="card pad muted">No hay trabajos.</div>}
        {jobs.map((j) => <JobRow key={j.id} job={j} />)}
      </div>
    </>
  )
}

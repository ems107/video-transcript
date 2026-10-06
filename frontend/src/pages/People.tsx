import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Person } from '../api'

type Draft = { id?: number; name: string; role: string; aliases: string; notes: string }

export default function People() {
  const [people, setPeople] = useState<Person[]>([])
  const [d, setD] = useState<Draft | null>(null)
  const [error, setError] = useState('')
  const load = () => { api.get<Person[]>('/api/people').then(setPeople) }
  useEffect(load, [])

  async function save() {
    if (!d) return
    setError('')
    const body = { name: d.name, role: d.role, notes: d.notes, aliases: d.aliases.split(',').map((a) => a.trim()).filter(Boolean) }
    try {
      if (d.id) await api.put(`/api/people/${d.id}`, body)
      else await api.post('/api/people', body)
      setD(null)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <>
      <div className="spread" style={{ marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Personas</h1>
        {!d && <button className="primary" onClick={() => setD({ name: '', role: '', aliases: '', notes: '' })}>+ Nueva persona</button>}
      </div>
      <p className="muted small">
        Cada vez que confirmas a una persona como hablante de un vídeo se guarda una muestra de su voz; con más muestras, el reconocimiento automático mejora.
      </p>
      {d && (
        <div className="card pad stack" style={{ marginBottom: '1rem', maxWidth: 700 }}>
          <div className="grid2">
            <label className="field"><span>Nombre</span><input autoFocus value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></label>
            <label className="field"><span>Rol</span><input value={d.role} onChange={(e) => setD({ ...d, role: e.target.value })} placeholder="Jefa de proyecto, cliente…" /></label>
          </div>
          <label className="field">
            <span>Otros nombres</span>
            <input value={d.aliases} onChange={(e) => setD({ ...d, aliases: e.target.value })} placeholder="Separados por comas: nombre en Teams, apodos…" />
            <small>Ayuda a reconocerla por el nombre que aparece en la videollamada.</small>
          </label>
          <label className="field"><span>Notas</span><textarea rows={2} value={d.notes} onChange={(e) => setD({ ...d, notes: e.target.value })} /></label>
          {error && <div className="error-box">{error}</div>}
          <div className="row">
            <button className="primary" onClick={save} disabled={!d.name.trim()}>Guardar</button>
            <button onClick={() => setD(null)}>Cancelar</button>
          </div>
        </div>
      )}
      <div className="card">
        <table className="tbl">
          <thead><tr><th>Nombre</th><th>Rol</th><th>Otros nombres</th><th>Muestras de voz</th><th>Vídeos</th><th /></tr></thead>
          <tbody>
            {people.map((p) => (
              <tr key={p.id}>
                <td><b>{p.name}</b></td>
                <td>{p.role}</td>
                <td className="small">{p.aliases.join(', ')}</td>
                <td>{p.voice_samples}</td>
                <td>{p.video_count > 0 ? <Link to={`/?person=${p.id}`}>{p.video_count}</Link> : 0}</td>
                <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <button className="sm" onClick={() => setD({ id: p.id, name: p.name, role: p.role, aliases: p.aliases.join(', '), notes: p.notes })}>Editar</button>{' '}
                  {p.voice_samples > 0 && (
                    <button className="sm" title="Olvidar las muestras de voz (si se asignaron mal)" onClick={async () => {
                      if (confirm(`¿Olvidar las ${p.voice_samples} muestras de voz de ${p.name}?`)) { await api.del(`/api/people/${p.id}/voices`); load() }
                    }}>Olvidar voz</button>
                  )}{' '}
                  <button className="sm danger" onClick={async () => {
                    if (confirm(`¿Eliminar a ${p.name}?`)) { await api.del(`/api/people/${p.id}`); load() }
                  }}>Eliminar</button>
                </td>
              </tr>
            ))}
            {people.length === 0 && <tr><td colSpan={6} className="muted">Aún no hay personas.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}

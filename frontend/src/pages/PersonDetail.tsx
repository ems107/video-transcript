import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, type Person, type PersonDetail as PD } from '../api'
import { KnowledgeList, ProposalList, VersionHistory } from '../knowledge'
import { fmtDate, fmtDuration, notifyKnowledge, plural } from '../util'
import { HelpLink } from '../HelpMarkdown'

type Tab = 'ficha' | 'propuestas' | 'historial'

function ManualForm({ p, onSaved }: { p: PD; onSaved: () => void }) {
  const [d, setD] = useState({ name: p.name, role: p.role, aliases: p.aliases.join(', '), notes: p.notes })
  const [error, setError] = useState('')
  async function save() {
    setError('')
    try {
      await api.put(`/api/people/${p.id}`, { ...d, aliases: d.aliases.split(',').map((a) => a.trim()).filter(Boolean) })
      notifyKnowledge()
      onSaved()
    } catch (e) {
      setError((e as Error).message)
    }
  }
  return (
    <div className="card pad stack">
      <h3 style={{ margin: 0 }}>Datos manuales</h3>
      <p className="muted small" style={{ margin: 0 }}>Esta parte es tuya: la IA nunca la modifica.</p>
      <div className="grid2">
        <label className="field"><span>Nombre</span><input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></label>
        <label className="field"><span>Rol</span><input value={d.role} onChange={(e) => setD({ ...d, role: e.target.value })} /></label>
      </div>
      <label className="field"><span>Otros nombres</span><input value={d.aliases} onChange={(e) => setD({ ...d, aliases: e.target.value })} placeholder="Separados por comas" /></label>
      <label className="field"><span>Notas</span><textarea rows={2} value={d.notes} onChange={(e) => setD({ ...d, notes: e.target.value })} /><small>Se incluyen en el contexto que recibe la IA.</small></label>
      {error && <div className="error-box">{error}</div>}
      <div><button className="primary" onClick={save} disabled={!d.name.trim()}>Guardar</button></div>
    </div>
  )
}

function MergeBox({ p, people }: { p: PD; people: Person[] }) {
  const nav = useNavigate()
  const [into, setInto] = useState('')
  const others = people.filter((x) => x.id !== p.id)
  if (!others.length) return null
  return (
    <div className="card pad stack">
      <h3 style={{ margin: 0 }}>Fusionar con otra persona <HelpLink to="personas#duplicados-y-fusion" /></h3>
      <p className="muted small" style={{ margin: 0 }}>
        Si «{p.name}» y otra persona son la misma, se unen su voz, sus vídeos, sus perfiles y lo aprendido. Se conserva la persona elegida.
      </p>
      <div className="row" style={{ flexWrap: 'nowrap' }}>
        <select value={into} onChange={(e) => setInto(e.target.value)}>
          <option value="">Elegir persona…</option>
          {others.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
        <button disabled={!into} onClick={async () => {
          const target = others.find((x) => String(x.id) === into)
          if (target && confirm(`¿Fusionar «${p.name}» en «${target.name}»? «${p.name}» dejará de existir como persona aparte. No se puede deshacer.`)) {
            await api.post(`/api/people/${p.id}/merge`, { into_id: target.id })
            notifyKnowledge()
            nav(`/personas/${target.id}`)
          }
        }}>Fusionar</button>
      </div>
    </div>
  )
}

export default function PersonDetail() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) || 'ficha'
  const [p, setP] = useState<PD | null>(null)
  const [people, setPeople] = useState<Person[]>([])
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.get<PD>(`/api/people/${id}`).then(setP).catch((e) => setError(e.message))
    api.get<Person[]>('/api/people').then(setPeople)
  }, [id])
  useEffect(load, [load])

  if (error) return <div className="error-box">{error}</div>
  if (!p) return <p className="muted">Cargando…</p>

  return (
    <>
      <div className="small"><Link to="/personas">← Personas</Link></div>
      <h1 style={{ margin: '0.25rem 0' }}>{p.name}</h1>
      <div className="muted small" style={{ marginBottom: '0.75rem' }}>
        {p.role && `${p.role} · `}{plural(p.stats.videos, 'vídeo', 'vídeos')}{p.stats.speaking_time > 0 && ` · ${fmtDuration(p.stats.speaking_time)} hablando`}
        {p.stats.last_seen && ` · última vez ${fmtDate(p.stats.last_seen)}`} · {plural(p.voice_samples, 'muestra', 'muestras')} de voz
        {p.profiles.length > 0 && <> · {p.profiles.map((pr, i) => <span key={pr.id}>{i > 0 && ', '}<Link to={`/perfiles/${pr.id}`}>{pr.name}</Link></span>)}</>}
      </div>
      <div className="tabs">
        {([['ficha', 'Ficha'], ['propuestas', 'Propuestas'], ['historial', 'Historial']] as [Tab, string][]).map(([k, label]) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => { params.set('tab', k); setParams(params, { replace: true }) }}>{label}</button>
        ))}
      </div>

      {tab === 'ficha' && (
        <div className="detail">
          <div className="stack">
            <ManualForm key={JSON.stringify([p.name, p.role, p.aliases, p.notes])} p={p} onSaved={load} />
            <MergeBox p={p} people={people} />
          </div>
          <div className="stack" style={{ minWidth: 0 }}>
            <h3 style={{ margin: 0 }}>Aprendido de los vídeos</h3>
            <KnowledgeList url={`/api/people/${p.id}/knowledge`} empty="Aún no hay nada aprendido de esta persona. Aparecerá al aceptar propuestas." />
            <div className="card pad">
              <h3 style={{ marginTop: 0 }}>Tareas asignadas</h3>
              {p.tasks.length ? (
                <table className="tbl">
                  <thead><tr><th>Tarea</th><th>Plazo</th><th>Vídeo</th></tr></thead>
                  <tbody>
                    {p.tasks.map((t, i) => (
                      <tr key={i}><td>{t.tarea}</td><td>{t.plazo || '—'}</td><td><Link to={`/videos/${t.video_id}?tab=tareas`}>{t.video_title}</Link></td></tr>
                    ))}
                  </tbody>
                </table>
              ) : <p className="muted small" style={{ marginBottom: 0 }}>Ninguna.</p>}
            </div>
            <div className="card pad">
              <h3 style={{ marginTop: 0 }}>Vídeos</h3>
              {p.videos.length ? (
                <ul style={{ margin: 0, paddingLeft: '1.2rem' }}>
                  {p.videos.map((v) => (
                    <li key={v.id}>
                      <Link to={`/videos/${v.id}`}>{v.title}</Link> <span className="muted small">· {fmtDate(v.date)} · {fmtDuration(v.speaking_time)}</span>
                      {!v.confirmed && <span className="pill warn" style={{ marginLeft: 4 }}>sin confirmar</span>}
                    </li>
                  ))}
                </ul>
              ) : <p className="muted small" style={{ marginBottom: 0 }}>Aún no aparece en ningún vídeo.</p>}
            </div>
          </div>
        </div>
      )}
      {tab === 'propuestas' && <ProposalList query={`person_id=${p.id}`} showOwner={false} empty="No hay propuestas pendientes sobre esta persona." />}
      {tab === 'historial' && <VersionHistory base={`/api/people/${p.id}`} onRestored={load} />}
    </>
  )
}

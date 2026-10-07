import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type GlossaryEntry, type Person, type Profile } from '../api'

export type Draft = Omit<Profile, 'id' | 'video_count' | 'learned_count' | 'pending_count'> & { id?: number }

const EMPTY: Draft = { name: '', description: '', context: '', extra_prompt: '', summary_sections: [], glossary: [], person_ids: [] }

// Formato de texto del glosario: una línea por término
//   Término | variante1, variante2 | definición
function glossaryToText(g: GlossaryEntry[]): string {
  return g.map((e) => [e.term, e.variants.join(', '), e.definition].join(' | ').replace(/( \| )+$/, '')).join('\n')
}

function textToGlossary(t: string): GlossaryEntry[] {
  return t.split('\n').map((line) => {
    const [term = '', variants = '', ...def] = line.split('|')
    return {
      term: term.trim(),
      variants: variants.split(',').map((v) => v.trim()).filter(Boolean),
      definition: def.join('|').trim(),
    }
  }).filter((e) => e.term)
}

export function Editor({ initial, people, onSaved, onCancel }: { initial: Draft; people: Person[]; onSaved: () => void; onCancel?: () => void }) {
  const [d, setD] = useState<Draft>(initial)
  const [glossary, setGlossary] = useState(glossaryToText(initial.glossary))
  const [sections, setSections] = useState(initial.summary_sections.join('\n'))
  const [error, setError] = useState('')
  const set = (k: keyof Draft, v: unknown) => setD({ ...d, [k]: v })

  async function save() {
    setError('')
    const body = { ...d, glossary: textToGlossary(glossary), summary_sections: sections.split('\n').map((s) => s.trim()).filter(Boolean) }
    try {
      if (d.id) await api.put(`/api/profiles/${d.id}`, body)
      else await api.post('/api/profiles', body)
      onSaved()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="card pad stack">
      {!d.id && <h2 style={{ marginTop: 0 }}>Nuevo perfil</h2>}
      {d.id && <p className="muted small" style={{ margin: 0 }}>Esta parte es tuya: la IA nunca la modifica. Lo que aprende va en «Aprendido».</p>}
      <div className="grid2">
        <label className="field"><span>Nombre</span><input value={d.name} onChange={(e) => set('name', e.target.value)} placeholder="Trabajo" /></label>
        <label className="field"><span>Descripción breve</span><input value={d.description} onChange={(e) => set('description', e.target.value)} placeholder="Reuniones del equipo de producto" /></label>
      </div>
      <label className="field">
        <span>Contexto y lógica de negocio</span>
        <textarea rows={6} value={d.context} onChange={(e) => set('context', e.target.value)}
          placeholder="A qué se dedica la empresa, productos, clientes, proyectos en curso, cómo se organiza el equipo, siglas internas…" />
        <small>El modelo lo usa para entender de qué se habla y redactar mejor el resumen.</small>
      </label>
      <label className="field">
        <span>Glosario</span>
        <textarea rows={8} value={glossary} onChange={(e) => setGlossary(e.target.value)} style={{ fontFamily: 'Consolas, monospace', fontSize: '0.85rem' }}
          placeholder={'Una línea por término:  Término | cómo se suele oír mal (separado por comas) | definición\nSalesforce | sels fors, sales fors | CRM de la empresa\nKubernetes | | Orquestador de contenedores\nOKR'} />
        <small>Se usa para que Whisper reconozca los términos y para corregir de forma conservadora lo que se oiga mal.</small>
      </label>
      <label className="field">
        <span>Personas habituales</span>
        <div className="row" style={{ gap: '0.5rem 1rem' }}>
          {people.length === 0 && <span className="muted small">Crea personas en la sección «Personas» (o al confirmar hablantes).</span>}
          {people.map((p) => (
            <label key={p.id} className="check small">
              <input type="checkbox" checked={d.person_ids.includes(p.id)}
                onChange={(e) => set('person_ids', e.target.checked ? [...d.person_ids, p.id] : d.person_ids.filter((x) => x !== p.id))} />
              {p.name}
            </label>
          ))}
        </div>
      </label>
      <div className="grid2">
        <label className="field">
          <span>Secciones del resumen</span>
          <textarea rows={4} value={sections} onChange={(e) => setSections(e.target.value)} placeholder={'Una por línea, p. ej.:\nContexto\nEstado de los proyectos\nRiesgos'} />
        </label>
        <label className="field">
          <span>Instrucciones adicionales para el análisis</span>
          <textarea rows={4} value={d.extra_prompt} onChange={(e) => set('extra_prompt', e.target.value)} placeholder="Céntrate en compromisos con clientes y fechas…" />
        </label>
      </div>
      {error && <div className="error-box">{error}</div>}
      <div className="row">
        <button className="primary" onClick={save} disabled={!d.name.trim()}>Guardar</button>
        {onCancel && <button onClick={onCancel}>Cancelar</button>}
      </div>
    </div>
  )
}

export default function Profiles() {
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [people, setPeople] = useState<Person[]>([])
  const [editing, setEditing] = useState<Draft | null>(null)

  const load = () => {
    api.get<Profile[]>('/api/profiles').then(setProfiles)
    api.get<Person[]>('/api/people').then(setPeople)
  }
  useEffect(load, [])

  return (
    <>
      <div className="spread" style={{ marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Perfiles</h1>
        {!editing && <button className="primary" onClick={() => setEditing(EMPTY)}>+ Nuevo perfil</button>}
      </div>
      {editing ? (
        <Editor initial={editing} people={people} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />
      ) : (
        <div className="stack">
          {profiles.length === 0 && <div className="card pad muted">Crea un perfil por tipo de vídeo (trabajo, clases, cliente X…) con su contexto, glosario y personas.</div>}
          {profiles.map((p) => (
            <div key={p.id} className="card pad spread">
              <div>
                <Link to={`/perfiles/${p.id}`}><b>{p.name}</b></Link> <span className="muted small">{p.description}</span>
                <div className="muted small">
                  {p.glossary.length} términos · {p.person_ids.length} personas · {p.video_count} vídeos · {p.learned_count} datos aprendidos
                  {p.pending_count > 0 && <> · <Link to={`/perfiles/${p.id}?tab=propuestas`}><span className="pill warn">{p.pending_count} propuestas</span></Link></>}
                </div>
              </div>
              <div className="row">
                <Link to={`/perfiles/${p.id}`}><button className="sm">Abrir</button></Link>
                <button className="sm danger" onClick={async () => {
                  if (confirm(`¿Eliminar el perfil «${p.name}»? Los vídeos analizados se conservan.`)) {
                    await api.del(`/api/profiles/${p.id}`)
                    load()
                  }
                }}>Eliminar</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

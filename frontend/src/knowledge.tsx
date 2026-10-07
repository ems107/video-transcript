// Componentes compartidos del conocimiento aprendido: propuestas, datos aceptados e historial.
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Evidence, type Knowledge, type Proposals, type Version } from './api'
import { fmtDate, fmtTs, notifyKnowledge } from './util'

const KIND_LABEL: Record<string, string> = {
  termino: 'Término',
  contexto: 'Contexto',
  seccion: 'Sección del resumen',
  dato: 'Dato',
  alias: 'Otro nombre',
  nueva_persona: 'Persona nueva',
}

const PROFILE_CATEGORIES: [string, string][] = [
  ['proyecto', 'Proyecto'], ['cliente', 'Cliente'], ['sistema', 'Sistema'], ['proceso', 'Proceso'], ['sigla', 'Sigla'], ['otro', 'Otro'],
]
const PERSON_CATEGORIES: [string, string][] = [
  ['cargo', 'Cargo'], ['organizacion', 'Organización'], ['equipo', 'Equipo'], ['responsabilidad', 'Responsabilidad'],
  ['proyecto', 'Proyecto'], ['conocimiento', 'Conocimiento'], ['relacion', 'Relación'], ['personal', 'Personal'], ['otro', 'Otro'],
]

function useKnowledgeReload(load: () => void) {
  useEffect(() => {
    window.addEventListener('knowledge-changed', load)
    return () => window.removeEventListener('knowledge-changed', load)
  }, [load])
}

function ownerLabel(k: Knowledge): string {
  const o = k.owner
  if (o.type === 'profile') return `Perfil «${o.name}»`
  if (o.type === 'new') return 'Persona nueva'
  return o.name
}

export function EvidenceView({ evidence }: { evidence: Evidence[] }) {
  if (!evidence.length) return null
  return (
    <details className="small" style={{ marginTop: '0.35rem' }}>
      <summary className="muted" style={{ cursor: 'pointer' }}>De dónde sale ({evidence.length} {evidence.length === 1 ? 'vídeo' : 'vídeos'})</summary>
      <div className="stack" style={{ gap: '0.5rem', marginTop: '0.4rem' }}>
        {evidence.map((e, i) => (
          <div key={i}>
            <Link to={`/videos/${e.video_id}${e.t != null ? `?t=${Math.floor(e.t)}&tab=transcripcion` : ''}`}>
              {e.video_title}{e.t != null && ` · ${fmtTs(e.t)}`}
            </Link>
            {e.lines.map((l, j) => (
              <div key={j} className="muted" style={{ paddingLeft: '0.75rem' }}>
                <span className="ts">{fmtTs(l.t)}</span> <b>{l.name}:</b> {l.text}
              </div>
            ))}
          </div>
        ))}
      </div>
    </details>
  )
}

type Edit = { text?: string; term?: string; definition?: string; title?: string; name?: string; category?: string }

function initialEdit(k: Knowledge): Edit {
  return { ...k.data, category: k.category } as Edit
}

function EditFields({ k, edit, setEdit }: { k: Knowledge; edit: Edit; setEdit: (e: Edit) => void }) {
  const cats = k.kind === 'contexto' ? PROFILE_CATEGORIES : k.kind === 'dato' ? PERSON_CATEGORIES : null
  return (
    <div className="stack" style={{ gap: '0.4rem', marginTop: '0.4rem' }}>
      {k.kind === 'termino' && (
        <div className="grid2">
          <input value={edit.term ?? ''} onChange={(e) => setEdit({ ...edit, term: e.target.value })} placeholder="Término" />
          <input value={edit.definition ?? ''} onChange={(e) => setEdit({ ...edit, definition: e.target.value })} placeholder="Definición (opcional)" />
        </div>
      )}
      {(k.kind === 'contexto' || k.kind === 'dato') && (
        <textarea rows={2} value={edit.text ?? ''} onChange={(e) => setEdit({ ...edit, text: e.target.value })} />
      )}
      {k.kind === 'seccion' && <input value={edit.title ?? ''} onChange={(e) => setEdit({ ...edit, title: e.target.value })} />}
      {(k.kind === 'alias' || k.kind === 'nueva_persona') && (
        <input value={edit.name ?? ''} onChange={(e) => setEdit({ ...edit, name: e.target.value })} placeholder="Nombre" />
      )}
      {cats && (
        <select value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value })} style={{ maxWidth: 240 }}>
          {cats.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      )}
    </div>
  )
}

function Body({ k }: { k: Knowledge }) {
  if (k.kind === 'termino') return <div><b>{k.data.term}</b>{k.data.definition && <span className="muted"> — {k.data.definition}</span>}</div>
  if (k.kind === 'nueva_persona') {
    return (
      <div>
        <b>{k.data.name}</b>
        <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.2rem' }}>
          {(k.data.datos ?? []).map((d, i) => <li key={i}>{d.text}</li>)}
        </ul>
      </div>
    )
  }
  return <div>{k.text}</div>
}

export function ProposalCard({ k, showOwner, onChange }: { k: Knowledge; showOwner: boolean; onChange: () => void }) {
  const [editing, setEditing] = useState(false)
  const [edit, setEdit] = useState<Edit>(initialEdit(k))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function decide(accept: boolean) {
    setBusy(true)
    setError('')
    try {
      const body = accept ? { accept: [k.id], edits: editing ? { [k.id]: edit } : {} } : { reject: [k.id] }
      const r = await api.post<{ en_espera: number }>('/api/proposals/decide', body)
      if (r.en_espera) setError('Antes hay que confirmar quién es este hablante en el vídeo.')
      else {
        notifyKnowledge()
        onChange()
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card pad" style={{ padding: '0.75rem 1rem' }}>
      <div className="spread" style={{ alignItems: 'flex-start', gap: '1rem' }}>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="row small" style={{ gap: '0.35rem', marginBottom: '0.25rem' }}>
            {showOwner && <span className="pill run">{ownerLabel(k)}</span>}
            <span className="pill">{KIND_LABEL[k.kind]}{k.category_label && ` · ${k.category_label}`}</span>
            {k.seen_count > 1 && <span className="pill ok">visto en {k.seen_count} vídeos</span>}
          </div>
          {editing ? <EditFields k={k} edit={edit} setEdit={setEdit} /> : <Body k={k} />}
          {k.replaces && <div className="small muted">Sustituye a: «{k.replaces.text}»</div>}
          <EvidenceView evidence={k.evidence} />
          {error && <div className="error-box small" style={{ marginTop: '0.4rem' }}>{error}</div>}
        </div>
        <div className="row" style={{ gap: '0.35rem', flexWrap: 'nowrap' }}>
          <button className="sm primary" disabled={busy} onClick={() => decide(true)}>{editing ? 'Guardar y aceptar' : 'Aceptar'}</button>
          {!editing && <button className="sm" disabled={busy} onClick={() => setEditing(true)}>Editar</button>}
          <button className="sm" disabled={busy} onClick={() => (editing ? setEditing(false) : decide(false))}>{editing ? 'Cancelar' : 'Rechazar'}</button>
        </div>
      </div>
    </div>
  )
}

// Propuestas pendientes agrupadas por vídeo
export function ProposalList({ query = '', showOwner = true, empty }: { query?: string; showOwner?: boolean; empty: string }) {
  const [data, setData] = useState<Proposals | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => {
    api.get<Proposals>(`/api/proposals${query ? `?${query}` : ''}`).then(setData)
  }, [query])
  useEffect(load, [load])
  useKnowledgeReload(load)

  if (!data) return <p className="muted">Cargando…</p>

  const groups = new Map<string, Knowledge[]>()
  for (const k of data.items) {
    const key = `${k.video_id ?? ''}|${k.video_title}`
    groups.set(key, [...(groups.get(key) ?? []), k])
  }

  async function bulk(ids: number[], accept: boolean) {
    setBusy(true)
    try {
      await api.post('/api/proposals/decide', accept ? { accept: ids } : { reject: ids })
      notifyKnowledge()
      load()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      {data.items.length === 0 && <div className="card pad muted">{empty}</div>}
      {[...groups.entries()].map(([key, items]) => {
        const [vid, title] = key.split('|')
        return (
          <div key={key} className="stack" style={{ gap: '0.5rem' }}>
            <div className="spread">
              <h3 style={{ margin: 0 }}>{vid ? <Link to={`/videos/${vid}`}>{title || 'Vídeo'}</Link> : 'Sin vídeo'}</h3>
              <div className="row" style={{ gap: '0.35rem' }}>
                <button className="sm" disabled={busy} onClick={() => bulk(items.map((k) => k.id), true)}>Aceptar todas ({items.length})</button>
                <button className="sm" disabled={busy} onClick={() => {
                  if (confirm(`¿Rechazar las ${items.length} propuestas? No se volverán a proponer.`)) bulk(items.map((k) => k.id), false)
                }}>Rechazar todas</button>
              </div>
            </div>
            {items.map((k) => <ProposalCard key={k.id} k={k} showOwner={showOwner} onChange={load} />)}
          </div>
        )
      })}
      {data.waiting.length > 0 && (
        <details className="card pad">
          <summary style={{ cursor: 'pointer' }}>
            <b>Esperando a que confirmes hablantes ({data.waiting.length})</b>
            <span className="muted small"> · se mostrarán cuando confirmes quién habla en cada vídeo</span>
          </summary>
          <ul className="small" style={{ marginBottom: 0 }}>
            {data.waiting.map((k) => (
              <li key={k.id}>
                <Link to={`/videos/${k.video_id}`}>{k.video_title}</Link> · {k.owner.name}: {k.text}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function KnowledgeRow({ k, onChange }: { k: Knowledge; onChange: () => void }) {
  const [editing, setEditing] = useState(false)
  const [edit, setEdit] = useState<Edit>(initialEdit(k))
  async function save() {
    await api.put(`/api/knowledge/${k.id}`, edit)
    setEditing(false)
    notifyKnowledge()
    onChange()
  }
  return (
    <div className="spread" style={{ alignItems: 'flex-start', gap: '1rem', padding: '0.5rem 0', borderTop: '1px solid var(--border)' }}>
      <div className="grow" style={{ minWidth: 0 }}>
        {editing ? <EditFields k={k} edit={edit} setEdit={setEdit} /> : <Body k={k} />}
        <div className="small muted">
          {k.seen_count === 1 ? 'Visto en 1 vídeo' : `Visto en ${k.seen_count} vídeos`}
          {k.last_seen_at && ` · última vez ${fmtDate(k.last_seen_at)}`}
        </div>
        <EvidenceView evidence={k.evidence} />
      </div>
      <div className="row" style={{ gap: '0.35rem', flexWrap: 'nowrap' }}>
        {editing ? (
          <>
            <button className="sm primary" onClick={save}>Guardar</button>
            <button className="sm" onClick={() => setEditing(false)}>Cancelar</button>
          </>
        ) : (
          <>
            <button className="sm" onClick={() => setEditing(true)}>Editar</button>
            <button className="sm" title="Deja de usarse; se puede recuperar desde el historial" onClick={async () => {
              if (confirm('¿Retirar este dato? Podrás recuperarlo desde el historial.')) {
                await api.post(`/api/knowledge/${k.id}/retire`)
                notifyKnowledge()
                onChange()
              }
            }}>Retirar</button>
          </>
        )}
      </div>
    </div>
  )
}

// Conocimiento aceptado, agrupado por tipo/categoría
export function KnowledgeList({ url, empty }: { url: string; empty: string }) {
  const [items, setItems] = useState<Knowledge[] | null>(null)
  const load = useCallback(() => { api.get<Knowledge[]>(url).then(setItems) }, [url])
  useEffect(load, [load])
  useKnowledgeReload(load)
  if (!items) return <p className="muted">Cargando…</p>
  if (!items.length) return <div className="card pad muted">{empty}</div>

  const groups = new Map<string, Knowledge[]>()
  for (const k of items) {
    const g = k.kind === 'termino' ? 'Términos' : k.kind === 'seccion' ? 'Secciones del resumen' : k.kind === 'alias' ? 'Otros nombres'
      : k.category_label || KIND_LABEL[k.kind]
    groups.set(g, [...(groups.get(g) ?? []), k])
  }
  return (
    <div className="stack">
      {[...groups.entries()].map(([g, ks]) => (
        <div key={g} className="card pad">
          <h3 style={{ margin: '0 0 0.25rem' }}>{g} <span className="muted small">({ks.length})</span></h3>
          {ks.map((k) => <KnowledgeRow key={k.id} k={k} onChange={load} />)}
        </div>
      ))}
    </div>
  )
}

const MANUAL_LABEL: Record<string, string> = {
  name: 'nombre', description: 'descripción', context: 'contexto', extra_prompt: 'instrucciones', summary_sections: 'secciones',
  glossary: 'glosario', personas: 'personas', role: 'rol', aliases: 'otros nombres', notes: 'notas',
}

function diffText(d: NonNullable<Version['diff']>): string {
  const parts = []
  if (d.added.length) parts.push(`+${d.added.length} añadido${d.added.length === 1 ? '' : 's'}`)
  if (d.removed.length) parts.push(`−${d.removed.length} retirado${d.removed.length === 1 ? '' : 's'}`)
  if (d.changed.length) parts.push(`${d.changed.length} editado${d.changed.length === 1 ? '' : 's'}`)
  if (d.manual.length) parts.push(`manual: ${d.manual.map((m) => MANUAL_LABEL[m] ?? m).join(', ')}`)
  return parts.join(' · ') || 'sin cambios visibles'
}

// Historial de versiones con restauración (base: /api/profiles/1 o /api/people/1)
export function VersionHistory({ base, onRestored }: { base: string; onRestored: () => void }) {
  const [versions, setVersions] = useState<Version[] | null>(null)
  const load = useCallback(() => { api.get<Version[]>(`${base}/versions`).then(setVersions) }, [base])
  useEffect(load, [load])
  useKnowledgeReload(load)
  if (!versions) return <p className="muted">Cargando…</p>
  if (!versions.length) return <div className="card pad muted">Aún no hay versiones: se crean con cada cambio.</div>
  return (
    <div className="card">
      <table className="tbl">
        <thead><tr><th>Fecha</th><th>Cambio</th><th>Detalle</th><th /></tr></thead>
        <tbody>
          {versions.map((v, i) => (
            <tr key={v.id}>
              <td style={{ whiteSpace: 'nowrap' }}>{fmtDate(v.created_at)}</td>
              <td>{v.reason}</td>
              <td className="small">
                {v.diff ? (
                  <details>
                    <summary style={{ cursor: 'pointer' }}>{diffText(v.diff)}</summary>
                    {v.diff.added.map((x, j) => <div key={`a${j}`} style={{ color: 'var(--ok)' }}>+ {x}</div>)}
                    {v.diff.removed.map((x, j) => <div key={`r${j}`} style={{ color: 'var(--danger)' }}>− {x}</div>)}
                    {v.diff.changed.map((x, j) => <div key={`c${j}`}>~ {x}</div>)}
                  </details>
                ) : <span className="muted">versión inicial</span>}
              </td>
              <td style={{ textAlign: 'right' }}>
                {i > 0 && (
                  <button className="sm" onClick={async () => {
                    if (confirm('¿Volver a esta versión? El estado actual también quedará guardado en el historial.')) {
                      await api.post(`${base}/versions/${v.id}/restore`)
                      notifyKnowledge()
                      onRestored()
                      load()
                    }
                  }}>Restaurar</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

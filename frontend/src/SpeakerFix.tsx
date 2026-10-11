import { useEffect, useRef, useState } from 'react'
import { api, type Person, type SegmentInfo, type SpeakerOverride, type VideoDetail, type Word } from './api'
import { fmtTs, notifyKnowledge } from './util'
import { HelpLink } from './HelpMarkdown'

type Scope = 'line' | 'part' | 'lines'

// Selector de persona: las del vídeo primero, después el resto, o una nueva
function PersonPicker({ video, people, value, onChange }: {
  video: VideoDetail
  people: Person[]
  value: { person_id?: number; new_person_name?: string }
  onChange: (v: { person_id?: number; new_person_name?: string }) => void
}) {
  const inVideo = new Set(video.speakers.map((s) => s.person_id).filter(Boolean))
  const sorted = [...people].sort((a, b) => Number(inVideo.has(b.id)) - Number(inVideo.has(a.id)) || a.name.localeCompare(b.name))
  return (
    <div className="stack" style={{ gap: '0.4rem' }}>
      <select value={value.person_id ?? ''} onChange={(e) => onChange(e.target.value ? { person_id: Number(e.target.value) } : {})}>
        <option value="">Elegir persona…</option>
        {sorted.map((p) => <option key={p.id} value={p.id}>{p.name}{inVideo.has(p.id) ? ' (en este vídeo)' : ''}</option>)}
      </select>
      <input placeholder="…o nombre de una persona nueva" value={value.new_person_name ?? ''}
        onChange={(e) => onChange(e.target.value ? { new_person_name: e.target.value } : {})} />
    </div>
  )
}

// Cambiar quién habla en un tramo: una línea, parte de ella o varias líneas seguidas
export function SpeakerFixDialog({ video, people, segment, onClose, onSaved }: {
  video: VideoDetail
  people: Person[]
  segment: SegmentInfo
  onClose: () => void
  onSaved: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [scope, setScope] = useState<Scope>('line')
  const [words, setWords] = useState<Word[] | null>(null)
  const [pick, setPick] = useState<[number, number] | null>(null)
  const [until, setUntil] = useState(segment.id)
  const [who, setWho] = useState<{ person_id?: number; new_person_name?: string }>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const next = video.segments.filter((s) => s.start >= segment.start).slice(0, 30)

  useEffect(() => { ref.current?.showModal() }, [])
  useEffect(() => {
    if (scope === 'part' && words === null) {
      api.get<Word[]>(`/api/videos/${video.id}/words?start=${segment.start}&end=${segment.end}`).then(setWords)
    }
  }, [scope, words, video.id, segment])

  const clickWord = (i: number) => setPick(!pick || pick[0] !== pick[1] ? [i, i] : [Math.min(pick[0], i), Math.max(pick[0], i)])
  const range = (): [number, number] | null => {
    if (scope === 'line') return [segment.start, segment.end]
    if (scope === 'lines') return [segment.start, video.segments.find((s) => s.id === until)?.end ?? segment.end]
    if (!words || !pick) return null
    return [words[pick[0]].start, words[pick[1]].end]
  }
  const r = range()
  const ready = r && (who.person_id || who.new_person_name?.trim())

  const save = async () => {
    setBusy(true)
    try {
      await api.post(`/api/videos/${video.id}/speaker-overrides`, { ranges: [r], ...who })
      notifyKnowledge()
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  return (
    <dialog ref={ref} className="card dialog" onClose={onClose}>
      <h3>Cambiar quién habla <HelpLink to="hablantes#cambiar-quien-habla" /></h3>
      <div className="stack">
        <p className="small muted">
          Se guarda como «de tal momento a tal momento habla esta persona»: se ve al momento en la transcripción y se
          mantiene aunque regeneres el análisis, también el completo. El resumen lo tendrá en cuenta al regenerar.
        </p>
        <div className="row small" style={{ gap: '1rem' }}>
          {([['line', 'Esta línea'], ['part', 'Parte de la línea'], ['lines', 'Varias líneas']] as [Scope, string][]).map(([k, label]) => (
            <label className="check" key={k}><input type="radio" checked={scope === k} onChange={() => setScope(k)} /> {label}</label>
          ))}
        </div>
        {scope === 'line' && <blockquote className="small">{segment.name}: «{segment.text}»</blockquote>}
        {scope === 'part' && (
          words === null ? <p className="muted small">Cargando palabras…</p>
            : words.length === 0 ? <p className="small">No hay datos de palabras para esta línea. Usa «Esta línea».</p>
              : (
                <div>
                  <p className="small muted">Pulsa la primera y la última palabra que dice la otra persona.</p>
                  <div className="words">
                    {words.map((w, i) => (
                      <button key={i} className={`word ${pick && i >= pick[0] && i <= pick[1] ? 'on' : ''}`} onClick={() => clickWord(i)}>{w.word}</button>
                    ))}
                  </div>
                </div>
              )
        )}
        {scope === 'lines' && (
          <label className="small">Hasta la línea
            <select value={until} onChange={(e) => setUntil(Number(e.target.value))}>
              {next.map((s) => <option key={s.id} value={s.id}>{fmtTs(s.start)} · {s.name}: {s.text.slice(0, 60)}</option>)}
            </select>
          </label>
        )}
        {r && <p className="small muted">Tramo: {fmtTs(r[0])} – {fmtTs(r[1])}</p>}
        <div><b className="small">Quién habla en ese tramo</b><PersonPicker video={video} people={people} value={who} onChange={setWho} /></div>
        {error && <p className="small danger-text">{error}</p>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button onClick={() => ref.current?.close()} disabled={busy}>Cancelar</button>
          <button className="primary" onClick={save} disabled={busy || !ready}>Guardar</button>
        </div>
      </div>
    </dialog>
  )
}

// Un hablante parece juntar dos voces: el usuario decide de quién es cada grupo
export function SplitDialog({ video, people, speakerId, seek, onClose, onSaved }: {
  video: VideoDetail
  people: Person[]
  speakerId: number
  seek: (t: number) => void
  onClose: () => void
  onSaved: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const sp = video.speakers.find((s) => s.id === speakerId)!
  const groups = sp.split?.groups ?? []
  const [who, setWho] = useState<{ person_id?: number; new_person_name?: string }[]>(groups.map(() => ({})))
  const [busy, setBusy] = useState(false)
  useEffect(() => { ref.current?.showModal() }, [])

  const save = async () => {
    setBusy(true)
    try {
      for (const [i, g] of groups.entries()) {
        if (who[i].person_id || who[i].new_person_name?.trim()) {
          await api.post(`/api/videos/${video.id}/speaker-overrides`, { ranges: g.ranges, ...who[i] })
        }
      }
      notifyKnowledge()
      onSaved()
    } finally {
      setBusy(false)
    }
  }

  return (
    <dialog ref={ref} className="card dialog" onClose={onClose}>
      <h3>¿Dos voces en «{sp.name}»? <HelpLink to="hablantes#dos-voces-en-un-hablante" /></h3>
      <div className="stack">
        <p className="small muted">
          Las intervenciones de este hablante forman dos grupos de voz distintos. Escucha unas frases de cada grupo y
          elige quién es. Lo que dejes sin elegir se queda como está. Se guarda como cambios manuales.
        </p>
        {groups.map((g, i) => (
          <div key={i} className="split-group">
            <b>Grupo {i + 1}</b> <span className="small muted">· {Math.round(g.seconds)} s en {g.ranges.length} intervenciones</span>
            <ul className="small">
              {g.samples.map((s) => (
                <li key={s.start}><button className="link" onClick={() => seek(s.start)}>{fmtTs(s.start)}</button> «{s.text.slice(0, 90)}»</li>
              ))}
            </ul>
            <PersonPicker video={video} people={people} value={who[i]} onChange={(v) => setWho(who.map((x, j) => (j === i ? v : x)))} />
          </div>
        ))}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button onClick={() => ref.current?.close()} disabled={busy}>Cancelar</button>
          <button className="primary" onClick={save} disabled={busy || !who.some((w) => w.person_id || w.new_person_name?.trim())}>Guardar</button>
        </div>
      </div>
    </dialog>
  )
}

// Cambios manuales de hablantes del vídeo, con opción de deshacerlos
export function OverridesList({ video, onChange }: { video: VideoDetail; onChange: () => void }) {
  const [items, setItems] = useState<SpeakerOverride[]>([])
  const [open, setOpen] = useState(false)
  useEffect(() => {
    api.get<SpeakerOverride[]>(`/api/videos/${video.id}/speaker-overrides`).then(setItems)
  }, [video])
  if (!items.length) return null
  return (
    <div className="small" style={{ marginTop: '0.75rem' }}>
      <button className="link" onClick={() => setOpen(!open)}>
        {open ? 'Ocultar' : 'Ver'} cambios manuales de hablantes ({items.length})
      </button>
      {open && (
        <ul className="corrections">
          {items.map((o) => (
            <li key={o.id}>
              <div className="correction-row">
                <span className="grow">{fmtTs(o.start)} – {fmtTs(o.end)}: {o.person_name}</span>
                <span className="actions">
                  <button className="sm" onClick={async () => { await api.del(`/api/speaker-overrides/${o.id}`); onChange() }}>Deshacer</button>
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

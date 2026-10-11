import { useEffect, useRef, useState } from 'react'
import { api, type RegenerateInfo, type RegenerateLevel } from './api'
import { fmtDuration, plural } from './util'

const OPTIONAL: { level: RegenerateLevel; title: string; text: string }[] = [
  {
    level: 'speakers',
    title: 'Volver a identificar a los hablantes',
    text: 'Vuelve a comprobar por la voz quién dice cada tramo y recalcula las propuestas de nombre con las voces y las personas que conoces ahora. Los hablantes que ya confirmaste y tus cambios manuales se mantienen.',
  },
  {
    level: 'screen',
    title: 'Volver a analizar la pantalla',
    text: 'Vuelve a elegir y a leer los fotogramas y a unificar los nombres vistos en pantalla. Útil si ha mejorado el análisis de imagen. Incluye volver a identificar a los hablantes.',
  },
  {
    level: 'full',
    title: 'Volver a transcribir y separar las voces (análisis completo)',
    text: 'Repite todo desde el audio. Los hablantes se vuelven a separar y pueden cambiar de número u orden, así que hay que volver a confirmarlos. La app los propondrá por su voz si ya la conoce: las huellas guardadas de tus personas se conservan.',
  },
]
const ORDER: RegenerateLevel[] = ['analysis', 'speakers', 'screen', 'full']

// Ventana para regenerar un vídeo: explica qué se repite y qué se conserva en cada nivel
export function RegenerateDialog({ videoId, onClose, onQueued }: { videoId: number; onClose: () => void; onQueued: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [info, setInfo] = useState<RegenerateInfo | null>(null)
  const [level, setLevel] = useState<RegenerateLevel>('analysis')
  const [busy, setBusy] = useState(false)
  const [spk, setSpk] = useState<{ min: string; max: string }>({ min: '', max: '' })
  const [error, setError] = useState('')

  useEffect(() => {
    ref.current?.showModal()
    api.get<RegenerateInfo>(`/api/videos/${videoId}/regenerate`).then((r) => {
      setInfo(r)
      setSpk({ min: r.min_speakers ? String(r.min_speakers) : '', max: r.max_speakers ? String(r.max_speakers) : '' })
      setLevel(r.levels.find((l) => l.available)?.level ?? 'analysis')  // sin datos intermedios: solo el completo
    }).catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [videoId])

  const byLevel = Object.fromEntries((info?.levels ?? []).map((l) => [l.level, l]))
  const depth = ORDER.indexOf(level)
  // Marcar un nivel incluye los anteriores; desmarcarlo vuelve al anterior
  const toggle = (l: RegenerateLevel) => setLevel(ORDER.indexOf(l) <= depth ? ORDER[ORDER.indexOf(l) - 1] : l)
  const chosen = byLevel[level]

  const run = async () => {
    setBusy(true)
    try {
      const extra = level === 'full' ? { min_speakers: Number(spk.min) || null, max_speakers: Number(spk.max) || null } : {}
      await api.post(`/api/videos/${videoId}/regenerate`, { level, ...extra })
      onQueued()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  return (
    <dialog ref={ref} className="card dialog" onClose={onClose}>
      <h3>Regenerar el análisis</h3>
      {!info ? <p className="muted">{error || 'Cargando…'}</p> : (
        <div className="stack">
          {byLevel.analysis?.available ? (
            <div className="small">
              <b>Siempre se repite</b>
              <ul>
                <li>La corrección de términos con el glosario actual</li>
                <li>El resumen: título, participantes, tareas, decisiones y pendientes, con tus correcciones</li>
                <li>Las propuestas de aprendizaje (las pendientes de este vídeo se sustituyen)</li>
                <li>Los documentos de la carpeta del vídeo</li>
              </ul>
              <b>Se conserva</b>: los hablantes confirmados, las huellas de voz, lo aceptado y lo rechazado, y tus correcciones.
            </div>
          ) : <p className="small">{byLevel.analysis?.reason} Solo está disponible el análisis completo.</p>}
          {OPTIONAL.map((o) => {
            const l = byLevel[o.level]
            const i = ORDER.indexOf(o.level)
            return (
              <label className="check" key={o.level}>
                <input type="checkbox" checked={i <= depth} disabled={!l?.available || (i < depth && byLevel[ORDER[depth]]?.available)}
                  onChange={() => toggle(o.level)} />
                <span>
                  <b>{o.title}</b>
                  <span className="small muted">{l?.available ? o.text : l?.reason}</span>
                </span>
              </label>
            )
          })}
          {level === 'full' && (
            <div className="small">
              <b>Número de hablantes</b> (opcional, ayuda a separar las voces)
              {info.on_screen ? <span className="muted"> · en pantalla se ven {info.on_screen} participantes</span> : null}
              <div className="row" style={{ flexWrap: 'nowrap', marginTop: '0.35rem' }}>
                <input type="number" min={1} placeholder="Mínimo" value={spk.min} onChange={(e) => setSpk({ ...spk, min: e.target.value })} />
                <input type="number" min={1} placeholder="Máximo" value={spk.max} onChange={(e) => setSpk({ ...spk, max: e.target.value })} />
              </div>
            </div>
          )}
          {level === 'full' && info.confirmed_speakers > 0 && (
            <p className="small danger-text">
              Se quitará la confirmación de {plural(info.confirmed_speakers, 'hablante', 'hablantes')} de este vídeo. Sus personas y sus voces se conservan.
            </p>
          )}
          {(level === 'screen' || level === 'full') && info.video_path && <p className="small muted">Usa el vídeo <code>{info.video_path}</code></p>}
          {error && <p className="small danger-text">{error}</p>}
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button onClick={() => ref.current?.close()} disabled={busy}>Cancelar</button>
            <button className="primary" onClick={run} disabled={busy || !chosen?.available}>
              Regenerar{chosen?.available ? ` (≈ ${fmtDuration(Math.max(chosen.seconds, 30))})` : ''}
            </button>
          </div>
        </div>
      )}
    </dialog>
  )
}

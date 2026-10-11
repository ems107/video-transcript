import { useEffect, useRef, useState } from 'react'
import { api, type RemovalInfo } from './api'
import { notifyKnowledge, plural } from './util'
import { HelpLink } from './HelpMarkdown'

type Options = { delete_files: boolean; delete_video: boolean; delete_original: boolean; forget: boolean }

// Ventana para quitar un vídeo. Sin marcar nada, la app lo olvida pero todo queda en el disco
export function RemoveDialog({ videoId, onClose, onRemoved }: { videoId: number; onClose: () => void; onRemoved: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [info, setInfo] = useState<RemovalInfo | null>(null)
  const [opts, setOpts] = useState<Options>({ delete_files: false, delete_video: false, delete_original: false, forget: false })
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<string[]>([])

  useEffect(() => {
    ref.current?.showModal()
    api.get<RemovalInfo>(`/api/videos/${videoId}/removal`).then(setInfo)
  }, [videoId])

  const set = (k: keyof Options) => (e: React.ChangeEvent<HTMLInputElement>) => setOpts({ ...opts, [k]: e.target.checked })
  const irreversible = opts.delete_files || opts.delete_video || opts.delete_original

  const remove = async () => {
    setBusy(true)
    const r = await api.post<{ ok: boolean; errors: string[] }>(`/api/videos/${videoId}/remove`, opts)
    if (opts.forget) notifyKnowledge()
    if (r.errors.length) {
      setErrors(r.errors)
      setBusy(false)
    } else onRemoved()
  }

  // Qué pasa con el vídeo si se borran los ficheros pero no el vídeo
  const videoFate = info?.video_in_folder && opts.delete_files && !opts.delete_video
    ? info.source_path ? 'La copia del vídeo de la carpeta se borra; el original se conserva.' : 'El vídeo vuelve a su ubicación original.'
    : ''

  return (
    <dialog ref={ref} className="card dialog" onClose={onClose}>
      <h3>Quitar el vídeo <HelpLink to="quitar" /></h3>
      {errors.length > 0 ? (
        <div className="stack">
          <p>El vídeo se ha quitado de la app, pero algunos ficheros no se pudieron borrar:</p>
          <ul className="small">{errors.map((e) => <li key={e}>{e}</li>)}</ul>
          <div className="row"><button onClick={onRemoved}>Cerrar</button></div>
        </div>
      ) : !info ? <p className="muted">Cargando…</p> : (
        <div className="stack">
          <p className="small muted">
            El vídeo desaparece de la app junto con sus propuestas pendientes. Sin marcar nada, todos sus ficheros
            se conservan para poder recuperarlo más adelante.
          </p>
          <label className="check">
            <input type="checkbox" checked={opts.delete_files} onChange={set('delete_files')} disabled={!info.folder && !info.work_dirs.length} />
            <span>
              <b>Borrar los ficheros del análisis</b>
              <span className="small muted">Transcripción, resumen, fotogramas y datos de trabajo. Se borran solo los ficheros que creó la app.
                {info.folder && <code>{info.folder}</code>}</span>
            </span>
          </label>
          <label className="check">
            <input type="checkbox" checked={opts.delete_video} onChange={set('delete_video')} disabled={!info.video_path} />
            <span>
              <b>Borrar el vídeo</b>
              <span className="small muted">{info.video_path ? <code>{info.video_path}</code> : 'No se encuentra el archivo de vídeo.'}</span>
            </span>
          </label>
          {info.source_path && (
            <label className="check">
              <input type="checkbox" checked={opts.delete_original} onChange={set('delete_original')} />
              <span>
                <b>Borrar también el vídeo original</b>
                <span className="small muted">La app trabajó con una copia. El original está en <code>{info.source_path}</code></span>
              </span>
            </label>
          )}
          <label className="check">
            <input type="checkbox" checked={opts.forget} onChange={set('forget')} />
            <span>
              <b>Olvidar lo aprendido de este vídeo</b>
              <span className="small muted">
                Retira el conocimiento aceptado que solo venía de este vídeo
                {info.voices > 0 && ` y ${plural(info.voices, 'huella de voz', 'huellas de voz')} guardadas al confirmar sus hablantes`}.
              </span>
            </span>
          </label>
          {videoFate && <p className="small">{videoFate}</p>}
          {irreversible && <p className="small danger-text">Los ficheros borrados no se pueden recuperar.</p>}
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button onClick={() => ref.current?.close()} disabled={busy}>Cancelar</button>
            <button className="danger" onClick={remove} disabled={busy}>{irreversible ? 'Quitar y borrar' : 'Quitar'}</button>
          </div>
        </div>
      )}
    </dialog>
  )
}

import { useEffect, useState } from 'react'
import type { Job } from './api'

export function fmtTs(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`
}

export function fmtDuration(seconds: number): string {
  if (!seconds) return '—'
  const m = Math.round(seconds / 60)
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' })
}

// Convierte "hh:mm:ss" o "mm:ss" en segundos
export function parseTs(ts: string): number | null {
  const m = ts.match(/(\d{1,2}):(\d{2})(?::(\d{2}))?/)
  if (!m) return null
  return m[3] !== undefined ? +m[1] * 3600 + +m[2] * 60 + +m[3] : +m[1] * 60 + +m[2]
}

// Estado de los trabajos en tiempo real (SSE)
export function useJobs(): Job[] {
  const [jobs, setJobs] = useState<Job[]>([])
  useEffect(() => {
    const es = new EventSource('/api/events')
    es.addEventListener('jobs', (e) => setJobs(JSON.parse((e as MessageEvent).data)))
    return () => es.close()
  }, [])
  return jobs
}

export const STATUS_LABEL: Record<string, string> = {
  queued: 'En cola',
  running: 'Procesando',
  done: 'Completado',
  error: 'Error',
  cancelled: 'Cancelado',
  processing: 'Procesando',
  pending: 'Pendiente',
}

const SPEAKER_COLORS = 8
export function speakerColor(order: number): string {
  return `var(--spk-${((order - 1) % SPEAKER_COLORS + SPEAKER_COLORS) % SPEAKER_COLORS})`
}

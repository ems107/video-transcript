// Cliente de la API local y tipos compartidos.

export type Job = {
  id: number
  video_id: number
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  stage: string
  stage_label: string
  progress: number
  message: string
  error: string
  options: Record<string, unknown>
  created_at: string
  started_at: string | null
  finished_at: string | null
  video_title: string
  video_source: string
}

export type VideoCard = {
  id: number
  title: string
  status: string
  duration: number
  recorded_at: string | null
  created_at: string
  folder: string
  profile: string | null
  profile_id: number | null
  summary: string
  people: string[]
  pending_speakers: number
  has_thumbnail: boolean
}

export type Task = { responsable: string; tarea: string; plazo: string; t: string }
export type Decision = { decision: string; t: string }

export type Analysis = {
  titulo?: string
  resumen_breve?: string
  resumen_detallado?: string
  participantes?: { nombre: string; papel: string }[]
  temas?: string[]
  tareas?: Task[]
  decisiones?: Decision[]
  pendientes?: string[]
}

export type SpeakerInfo = {
  id: number
  label: string
  name: string
  order: number
  person_id: number | null
  confirmed: boolean
  is_owner: boolean
  suggested_person_id: number | null
  suggested_person_name: string | null
  suggested_name: string
  source: string
  confidence: number
  speaking_time: number
  visual_hints: Record<string, number>
  has_embedding: boolean
}

export type SegmentInfo = {
  id: number
  start: number
  end: number
  speaker: string
  name: string
  text: string
  original_text: string
  corrections: { original: string; suggestion: string; kind: string; score: number }[]
}

export type KeyframeInfo = {
  id: number
  t: number
  scene_type: string
  description: string
  visible_text: string
  participants: string[]
  active_speaker: string
}

export type VideoDetail = VideoCard & {
  source_path: string
  video_path: string
  analysis: Analysis
  speakers: SpeakerInfo[]
  segments: SegmentInfo[]
  keyframes: KeyframeInfo[]
  job: Job | null
}

export type GlossaryEntry = { term: string; variants: string[]; definition: string }

export type Profile = {
  id: number
  name: string
  description: string
  context: string
  extra_prompt: string
  summary_sections: string[]
  glossary: GlossaryEntry[]
  person_ids: number[]
  video_count: number
}

export type Person = {
  id: number
  name: string
  role: string
  aliases: string[]
  notes: string
  voice_samples: number
  video_count: number
}

export type ProbeInfo = {
  path: string
  duration: number
  size: number
  audio_tracks: { index: number; codec: string; channels: number; title: string; language: string }[]
  video: boolean
  width: number | null
  height: number | null
  recorded_at: string
}

export type SearchHit = {
  kind: 'segment' | 'summary' | 'title' | 'frame'
  video_id: number
  video_title: string
  t: number
  speaker: string
  snippet: string
}

export type Settings = Record<string, string | number>

export type Status = { version: string; checks: Record<string, boolean>; ready: boolean; current_job: number | null }

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const data = await res.json()
      msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* respuesta sin JSON */
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(url: string) => req<T>('GET', url),
  post: <T>(url: string, body?: unknown) => req<T>('POST', url, body ?? {}),
  put: <T>(url: string, body: unknown) => req<T>('PUT', url, body),
  del: <T>(url: string) => req<T>('DELETE', url),
}

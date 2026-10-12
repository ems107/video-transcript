// Cliente de la API local y tipos compartidos.

export type Job = {
  id: number
  video_id: number
  status: 'queued' | 'running' | 'waiting' | 'done' | 'error' | 'cancelled' // waiting: espera la revisión de otro vídeo
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
  review: ReviewState
}

// Revisión del vídeo: pendiente → aplicando → propuestas (queda algo por decidir) → revisado
export type ReviewState = 'pendiente' | 'aplicando' | 'propuestas' | 'revisado'
export type ReviewChange = { kind: 'correcciones' | 'tramos' | 'hablantes'; n: number; label: string }
export type ReviewInfo = {
  state: ReviewState
  changes: ReviewChange[] // cambios del usuario que aún no se han aplicado
  pending: { propuestas: number; seguimiento: number } // lo que queda por decidir tras aplicar
  waiting: { id: number; title: string }[] // vídeos que esperan a que se revise este
}
export type ApplyInfo = { stages: string[]; seconds: number; changes: ReviewChange[] }

export type Task = { responsable: string; tarea: string; plazo: string; t: string }
export type Decision = { decision: string; t: string }

export type Pending = { pendiente: string; t: string }

export type Analysis = {
  titulo?: string
  resumen_breve?: string
  resumen_detallado?: string
  participantes?: { nombre: string; papel: string }[]
  temas?: string[]
  tareas?: Task[]
  decisiones?: Decision[]
  pendientes?: (string | Pending)[] // texto solo en vídeos analizados antes de la 1.5.0
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
  reason: string // por qué se propone (identidad deducida del contexto)
  aliases: string[] // apodos con que se le llama en el vídeo
  split: SpeakerSplit | null // parece juntar dos voces
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
  voice: '' | 'reasignada' | 'dudosa' // comprobación por la voz
}

export type Word = { word: string; start: number; end: number }
export type SpeakerOverride = { id: number; start: number; end: number; person_id: number; person_name: string }
export type SpeakerSplit = {
  silhouette: number
  groups: { seconds: number; ranges: [number, number][]; samples: { start: number; end: number; text: string }[] }[]
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
  video_corrections: { id: number; text: string; updated_at: string; applied: boolean }[] // applied: el análisis actual ya la tiene en cuenta
  corrections_pending: boolean // hay correcciones que el análisis actual aún no tiene en cuenta
  overrides_pending: boolean // hay cambios manuales de hablantes que el resumen aún no tiene en cuenta
  followups: { id: number; name: string; status: FollowupStatus; applied: boolean }[] // applied: el estado ya incluye este vídeo
  review: ReviewInfo
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
  learned_count: number
  pending_count: number
}

export type Person = {
  id: number
  name: string
  role: string
  aliases: string[]
  notes: string
  voice_samples: number
  video_count: number
  learned_count: number
}

export type PersonDetail = Person & {
  videos: { id: number; title: string; date: string; confirmed: boolean; speaking_time: number; status: string }[]
  tasks: (Task & { video_id: number; video_title: string; date: string })[]
  profiles: { id: number; name: string }[]
  stats: { videos: number; confirmed_videos: number; speaking_time: number; last_seen: string | null }
}

export type Duplicate = { a: number; b: number; a_name: string; b_name: string; reasons: ('nombre' | 'voz')[] }

// Conocimiento aprendido (aceptado) o propuesto por la IA
export type KnowledgeKind = 'termino' | 'contexto' | 'seccion' | 'dato' | 'alias' | 'nueva_persona' | 'correccion'
export type EvidenceLine = { t: number; label: string; name: string; text: string }
export type Evidence = { video_id: number; video_title: string; t: number | null; lines: EvidenceLine[] }
export type Knowledge = {
  id: number
  kind: KnowledgeKind
  category: string
  category_label: string
  data: {
    text?: string
    term?: string
    definition?: string
    forms?: string[] // otras formas del mismo nombre (términos)
    pantalla?: { relacion: 'relacionado' | 'dudoso'; motivo: string } // término visto solo en pantalla
    variants?: string[] // corrección de transcripción: cómo se oye mal el término
    fuente?: 'usuario' | 'pantalla' | 'glosario' | 'ia' // de dónde sale la forma correcta
    motivo?: string
    juicio?: { valor: 'util' | 'dudosa' | 'descartar'; motivo: string } // pasada de juicio de la IA
    title?: string
    name?: string
    datos?: { category: string; text: string; t: number | null }[]
  }
  text: string
  status: 'propuesto' | 'aceptado' | 'rechazado' | 'retirado' | 'descartado_ia'
  seen_count: number
  video_id: number | null
  video_title: string
  owner: { type: 'profile' | 'person' | 'speaker' | 'new'; id: number | null; name: string }
  evidence: Evidence[]
  replaces: { id: number; text: string } | null
  last_seen_at: string | null
}
export type Proposals = { items: Knowledge[]; waiting: Knowledge[]; discarded: Knowledge[] } // discarded: solo con video_id
export type Version = {
  id: number
  created_at: string
  reason: string
  diff: { added: string[]; removed: string[]; changed: string[]; manual: string[] } | null
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

export type Status = {
  version: string
  checks: Record<string, boolean>
  ready: boolean
  current_job: number | null
  pending_proposals: number
  to_review: number // vídeos analizados pendientes de revisar
}

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

export type RegenerateLevel = 'analysis' | 'speakers' | 'screen' | 'full'
export type RegenerateInfo = {
  levels: { level: RegenerateLevel; available: boolean; reason: string; seconds: number }[]
  video_path: string | null
  confirmed_speakers: number
  on_screen: number | null // participantes distintos vistos en pantalla
  min_speakers: number | null
  max_speakers: number | null
  followups: { id: number; name: string; status: FollowupStatus; seconds: number }[] // seconds: rehacer su estado desde este vídeo
}

export type RemovalInfo = {
  folder: string | null
  video_path: string | null
  source_path: string | null // original, solo si la app trabajó con una copia
  video_in_folder: boolean
  work_dirs: string[]
  voices: number
  pending_proposals: number
  followups: { id: number; name: string; applied: boolean }[]
}

// Seguimientos: continuidad de un tema entre vídeos
export type FollowupStatus = 'abierto' | 'archivado'
export type FollowupKind = 'tarea' | 'decision' | 'duda'
export type FollowupEvent = {
  video_id: number | null
  video_title: string
  date: string | null // fecha de grabación del vídeo (null si es un cambio manual)
  t: string
  evento: 'creada' | 'avanza' | 'hecha' | 'descartada' | 'reabierta' | 'cambiada' | 'anulada' | 'resuelta'
  nota: string
  cita?: string // la frase del vídeo que lo dice (comprobada)
  posible?: FollowupEvent['evento'] // la IA cree que pasó, sin una frase que lo demuestre: lo confirma el usuario
  descartado?: boolean // el usuario dice que ese cambio «posible» no pasó
  source: 'ia' | 'manual'
  at: string
}
export type FollowupItem = {
  id: number
  kind: FollowupKind
  text: string
  owner: string
  due: string
  status: string
  manual: boolean
  events: FollowupEvent[]
  review: { tipo?: 'duplicado'; de?: number | null; texto?: string; motivo?: string } // duda de la IA que decides tú
}
export type Followup = {
  id: number
  name: string
  description: string
  status: FollowupStatus
  summary: string
  summary_manual: boolean // el usuario lo ha editado: la IA ya no lo reescribe
  summary_ai: string // resumen nuevo de la IA cuando el vigente es el del usuario
  stale_from: string | null // el estado no está al día desde esta fecha
  stale_reason: string
  folder: string
  created_at: string
  updated_at: string
  n_videos: number
  last_date: string | null
  open_tasks: number
  profile_id: number | null // perfil más usado en sus vídeos
  busy: boolean // hay un trabajo en cola que lo va a actualizar
  job_id: number | null
  rebuild_seconds: number | null
  pending_videos: { id: number; title: string }[] // se aplicarán al estado cuando los revises
  to_review: number // puntos con algo que decidir
}
export type FollowupDetail = Followup & {
  videos: {
    video_id: number; title: string; date: string; duration: number; status: string; review: ReviewState
    applied: boolean; contribution: string
    rebuild_seconds: number // rehacer el estado desde este vídeo
  }[]
  items: FollowupItem[]
}
// Punto de un seguimiento con una duda de la IA salida de un vídeo (pantalla «Revisar este vídeo»)
export type ReviewItem = {
  followup_id: number
  followup_name: string
  reasons: ('duplicado' | 'posible')[]
  item: FollowupItem
  same_as: { id: number; kind: FollowupKind; text: string; status: string; hidden: boolean } | null
  possible: FollowupEvent | null
}
export type FollowupVersion = { id: number; reason: string; created_at: string; items: number; videos: number }

export const api = {
  get: <T>(url: string) => req<T>('GET', url),
  post: <T>(url: string, body?: unknown) => req<T>('POST', url, body ?? {}),
  put: <T>(url: string, body: unknown) => req<T>('PUT', url, body),
  del: <T>(url: string) => req<T>('DELETE', url),
}

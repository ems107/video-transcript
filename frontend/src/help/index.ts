// Páginas de la ayuda: un Markdown por página en esta carpeta, con cabecera
// ---
// titulo: Hablantes
// seccion: Cada vídeo
// orden: 20
// claves: voz, confirmar
// ---

export const SECTIONS = ['Empezar', 'Cada vídeo', 'Conocimiento', 'Otros', 'Por dentro', 'Ayuda']

export type HelpPage = {
  slug: string
  title: string
  section: string
  order: number
  keywords: string
  body: string
}

const files = import.meta.glob('./*.md', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

function parse(path: string, raw: string): HelpPage {
  const slug = path.replace('./', '').replace('.md', '')
  const m = raw.replace(/\r\n/g, '\n').match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/)
  const meta: Record<string, string> = {}
  for (const line of (m?.[1] ?? '').split('\n')) {
    const i = line.indexOf(':')
    if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim()
  }
  return {
    slug,
    title: meta.titulo ?? slug,
    section: meta.seccion ?? 'Otros',
    order: Number(meta.orden ?? 999),
    keywords: meta.claves ?? '',
    body: m?.[2] ?? raw,
  }
}

export const PAGES: HelpPage[] = Object.entries(files)
  .map(([path, raw]) => parse(path, raw))
  .sort((a, b) => SECTIONS.indexOf(a.section) - SECTIONS.indexOf(b.section) || a.order - b.order)

export function findPage(slug: string | undefined): HelpPage | undefined {
  return PAGES.find((p) => p.slug === slug)
}

// Identificador de un encabezado para los enlaces «ayuda:página#ancla»
export function slugify(text: string): string {
  return text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

// Quita la sintaxis Markdown para buscar en el texto
export function plain(text: string): string {
  return text.replace(/:::tecnico.*|:::/g, ' ').replace(/[#*_`>|[\]()!-]/g, ' ').replace(/\s+/g, ' ')
}

export type Values = Record<string, unknown> | null

// Valores en vivo: {{v:clave}} → el ajuste o umbral actual de la app, con formato español
export function fillValues(text: string, values: Values): string {
  return text.replace(/\{\{v:([a-z0-9_]+)\}\}/g, (_, key: string) => {
    if (!values) return '…'
    const v = values[key]
    if (typeof v === 'number') return v.toLocaleString('es-ES', { maximumFractionDigits: 2 })
    if (typeof v === 'boolean') return v ? 'sí' : 'no'
    return v === undefined || v === null ? `¿${key}?` : String(v)
  })
}


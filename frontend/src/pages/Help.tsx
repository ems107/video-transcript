import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { findPage, PAGES, plain, SECTIONS, slugify, type Values } from '../help'
import { HelpMarkdown } from '../HelpMarkdown'

const TECH_KEY = 'ayuda-detalles-tecnicos'

function readTech(): boolean {
  try {
    return localStorage.getItem(TECH_KEY) === '1'
  } catch {
    return false
  }
}

export default function Help() {
  const { pagina } = useParams()
  const nav = useNavigate()
  const { hash } = useLocation()
  const [values, setValues] = useState<Values>(null)
  const [changelog, setChangelog] = useState('')
  const [query, setQuery] = useState('')
  const [showTech, setShowTech] = useState(readTech)
  const page = findPage(pagina) ?? PAGES[0]

  useEffect(() => {
    api.get<Record<string, unknown>>('/api/help/values').then(setValues).catch(() => setValues({}))
  }, [])
  useEffect(() => {
    if (page?.slug === 'novedades' && !changelog) {
      api.get<{ text: string }>('/api/help/changelog').then((r) => setChangelog(r.text))
    }
  }, [page, changelog])
  // Ir al ancla (#seccion) al cambiar de página o de ancla
  useEffect(() => {
    const id = decodeURIComponent(hash.slice(1))
    const el = id ? document.getElementById(id) : null
    if (el) el.scrollIntoView({ block: 'start' })
    else window.scrollTo(0, 0)
  }, [page, hash, values, changelog])

  const toggleTech = (v: boolean) => {
    setShowTech(v)
    try {
      localStorage.setItem(TECH_KEY, v ? '1' : '0')
    } catch {
      // sin almacenamiento: solo para esta visita
    }
  }

  const q = query.trim().toLowerCase()
  const results = useMemo(() => !q ? [] : PAGES.map((p) => {
    const text = plain(p.body)
    const i = text.toLowerCase().indexOf(q)
    const hit = p.title.toLowerCase().includes(q) || p.keywords.toLowerCase().includes(q)
    return { p, i, hit, snippet: i >= 0 ? text.slice(Math.max(0, i - 50), i + 90) : '' }
  }).filter((r) => r.hit || r.i >= 0), [q])

  if (!page) return <p className="muted">No hay páginas de ayuda.</p>
  const body = page.slug === 'novedades' ? `${page.body}\n\n${changelog.replace(/^# .*\n/, '')}` : page.body
  const toc = [...body.matchAll(/^## (.+)$/gm)].map((m) => m[1].trim())
  const idx = PAGES.indexOf(page)
  const prev = PAGES[idx - 1]
  const next = PAGES[idx + 1]

  return (
    <div className="help">
      <aside className="help-nav">
        <input placeholder="Buscar en la ayuda…" value={query} onChange={(e) => setQuery(e.target.value)} />
        {q ? (
          <div className="help-results">
            {results.length === 0 && <p className="small muted">Sin resultados.</p>}
            {results.map(({ p, snippet }) => (
              <button key={p.slug} className="link help-result" onClick={() => { nav(`/ayuda/${p.slug}`); setQuery('') }}>
                <b>{p.title}</b>
                {snippet && <span className="small muted">…{snippet}…</span>}
              </button>
            ))}
          </div>
        ) : SECTIONS.map((s) => (
          <div key={s} className="help-section">
            <div className="help-section-title">{s}</div>
            {PAGES.filter((p) => p.section === s).map((p) => (
              <Link key={p.slug} to={`/ayuda/${p.slug}`} className={p.slug === page.slug ? 'active' : ''}>{p.title}</Link>
            ))}
          </div>
        ))}
      </aside>
      <article className="card pad help-page">
        <div className="spread" style={{ alignItems: 'flex-start' }}>
          <div className="grow">
            <div className="small muted">{page.section}</div>
            <h1 style={{ margin: '0.15rem 0 0.75rem' }}>{page.title}</h1>
          </div>
          <label className="check small" title="Los detalles técnicos explican cómo está hecho por dentro; no hacen falta para usar la app">
            <input type="checkbox" checked={showTech} onChange={(e) => toggleTech(e.target.checked)} /> Mostrar detalles técnicos
          </label>
        </div>
        {toc.length > 2 && (
          <nav className="help-toc small">
            {toc.map((h) => <a key={h} href={`#${slugify(h)}`} onClick={(e) => { e.preventDefault(); nav(`#${slugify(h)}`) }}>{h}</a>)}
          </nav>
        )}
        <HelpMarkdown text={body} values={values} showTech={showTech} />
        <div className="spread help-pager">
          {prev ? <Link to={`/ayuda/${prev.slug}`}>← {prev.title}</Link> : <span />}
          {next ? <Link to={`/ayuda/${next.slug}`}>{next.title} →</Link> : <span />}
        </div>
      </article>
    </div>
  )
}

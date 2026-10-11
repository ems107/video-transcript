import { Children, isValidElement, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link } from 'react-router-dom'
import { fillValues, slugify, type Values } from './help'

function textOf(node: ReactNode): string {
  return Children.toArray(node).map((c) => (typeof c === 'string' || typeof c === 'number' ? String(c)
    : isValidElement<{ children?: ReactNode }>(c) ? textOf(c.props.children) : '')).join('')
}

const heading = (Tag: 'h2' | 'h3') => ({ children }: { children?: ReactNode }) => <Tag id={slugify(textOf(children))}>{children}</Tag>

const components: Components = {
  h2: heading('h2'),
  h3: heading('h3'),
  a: ({ href, children }) => {
    if (href?.startsWith('ayuda:')) {
      const [page, anchor] = href.slice(6).split('#')
      return <Link to={`/ayuda/${page}${anchor ? `#${anchor}` : ''}`}>{children}</Link>
    }
    return <a href={href} target="_blank" rel="noreferrer">{children}</a>
  },
  img: ({ src, alt }) => {
    const s = typeof src === 'string' ? src : ''
    const url = s.startsWith('captura:') ? `/capturas/${s.slice(8)}.png` : s
    return (
      <figure className="help-shot">
        <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={alt ?? ''} loading="lazy" /></a>
        {alt && <figcaption>{alt}</figcaption>}
      </figure>
    )
  },
}

function Md({ text }: { text: string }) {
  // El contenido es nuestro: se dejan pasar los esquemas propios «ayuda:» y «captura:», que react-markdown
  // descartaría por seguridad
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} urlTransform={(url) => url}>{text}</ReactMarkdown>
}

// Una página de ayuda: Markdown normal y bloques «:::tecnico Título … :::» plegables y diferenciados
export function HelpMarkdown({ text, values, showTech }: { text: string; values: Values; showTech: boolean }) {
  const parts: { tech: boolean; title: string; body: string }[] = []
  const re = /^:::tecnico[ \t]*(.*)\n([\s\S]*?)\n:::[ \t]*$/gm
  const filled = fillValues(text, values)
  let last = 0
  for (const m of filled.matchAll(re)) {
    parts.push({ tech: false, title: '', body: filled.slice(last, m.index) })
    parts.push({ tech: true, title: m[1].trim(), body: m[2] })
    last = (m.index ?? 0) + m[0].length
  }
  parts.push({ tech: false, title: '', body: filled.slice(last) })
  return (
    <div className="md help-md">
      {parts.map((p, i) => p.tech ? (
        <details key={`${i}-${showTech}`} className="tech" open={showTech}>
          <summary><span className="tech-tag">Detalle técnico</span>{p.title && ` ${p.title}`}</summary>
          <Md text={p.body} />
        </details>
      ) : <Md key={i} text={p.body} />)}
    </div>
  )
}

// Enlace «?» a la ayuda desde cualquier pantalla
export function HelpLink({ to, label }: { to: string; label?: string }) {
  return (
    <Link className="help-link" to={`/ayuda/${to}`} title={label ?? 'Ver la ayuda'} onClick={(e) => e.stopPropagation()}>?</Link>
  )
}

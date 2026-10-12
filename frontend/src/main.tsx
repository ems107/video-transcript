import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import './index.css'
import { ApiError } from './api'

// Los errores de JavaScript van al registro de la app (una vez por mensaje): sin esto, un fallo de la web
// no deja rastro en el servidor
const reported = new Set<string>()
function reportError(message: string, stack = '') {
  if (!message || reported.has(message)) return
  reported.add(message)
  fetch('/api/client-log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, stack, url: location.pathname }),
  }).catch(() => {})
}
window.addEventListener('error', (e) => reportError(e.message, e.error instanceof Error ? e.error.stack ?? '' : ''))
window.addEventListener('unhandledrejection', (e) => {
  const r: unknown = e.reason
  if (r instanceof ApiError) return
  reportError(r instanceof Error ? r.message : String(r), r instanceof Error ? r.stack ?? '' : '')
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)

import type { FollowupEvent, FollowupKind } from './api'

// Estados posibles de cada tipo de punto, el primero es el inicial (igual que en backend/app/followups.py)
export const STATUSES: Record<FollowupKind, string[]> = {
  tarea: ['abierta', 'hecha', 'descartada'],
  decision: ['vigente', 'cambiada', 'anulada'],
  duda: ['abierta', 'resuelta'],
}
export const KIND_TITLES: Record<FollowupKind, string> = { tarea: 'Tareas', decision: 'Decisiones', duda: 'Dudas y pendientes' }
export const KIND_ONE: Record<FollowupKind, string> = { tarea: 'tarea', decision: 'decisión', duda: 'duda' }
export const EVENT_LABELS: Record<FollowupEvent['evento'], string> = {
  creada: 'aparece', avanza: 'avanza', hecha: 'hecha', descartada: 'descartada', reabierta: 'reabierta',
  cambiada: 'cambiada', anulada: 'anulada', resuelta: 'resuelta',
}

export function statusClass(kind: FollowupKind, status: string): string {
  if (status === STATUSES[kind][0]) return 'pill run'
  return ['hecha', 'resuelta'].includes(status) ? 'pill ok' : 'pill'
}

// Estado en que deja un punto cada cambio «posible» al confirmarlo
export const STATUS_AFTER: Record<string, string> = {
  hecha: 'hecha', descartada: 'descartada', cambiada: 'cambiada', anulada: 'anulada', resuelta: 'resuelta',
}

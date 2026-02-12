import type { Monitor, MonitorCreate, MonitorUpdate, PriceHistory, HealthStatus } from '../types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API error ${res.status}: ${body}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  getHealth: () => request<HealthStatus>('/health'),

  listMonitors: () => request<Monitor[]>('/monitors'),

  getMonitor: (id: number) => request<Monitor>(`/monitors/${id}`),

  createMonitor: (data: MonitorCreate) =>
    request<Monitor>('/monitors', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateMonitor: (id: number, data: MonitorUpdate) =>
    request<Monitor>(`/monitors/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteMonitor: (id: number) =>
    request<void>(`/monitors/${id}`, { method: 'DELETE' }),

  toggleAlerts: (id: number) =>
    request<Monitor>(`/monitors/${id}/toggle-alerts`, { method: 'PATCH' }),

  getHistory: (id: number, days: number = 7) =>
    request<PriceHistory[]>(`/monitors/${id}/history?days=${days}`),

  checkNow: (id: number) =>
    request<Record<string, unknown>>(`/monitors/${id}/check-now`, { method: 'POST' }),
}

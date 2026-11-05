export type Row = Record<string, any>
export type Catalog = Record<string, Row[]>
export const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export async function api<T = any>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api/product${path}`, {
    method, headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const value = await response.json()
  if (!response.ok) throw new Error([value.message || 'Request failed', ...(value.errors || [])].join('\n'))
  return value.data
}
export async function solvers(): Promise<Row[]> {
  const response = await fetch('/api/solvers')
  if (!response.ok) throw new Error('Cannot reach the scheduling service')
  return (await response.json()).solvers
}
export function minutes(value: string) { const [h, m] = value.split(':').map(Number); return h * 60 + m }
export function clock(value: number) { return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}` }
export function terminal(state: string) { return !['queued', 'running'].includes(state) }

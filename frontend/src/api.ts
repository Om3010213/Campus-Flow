export type Row = Record<string, any>
export type Catalog = Record<string, Row[]>
export const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
let csrfToken = ''
let bootstrap: Promise<any> | null = null

export function loadSession(): Promise<any> {
  if (!bootstrap) bootstrap = requestJson('/api/auth/session').finally(() => { bootstrap = null })
  return bootstrap
}

export async function requestJson(path: string, method = 'GET', body?: unknown): Promise<any> {
  if (!['GET', 'HEAD'].includes(method) && !csrfToken) await loadSession()
  const response = await fetch(path, {
    method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json',
      ...(!['GET', 'HEAD'].includes(method) ? { 'X-CSRF-Token': csrfToken } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const value = await response.json()
  if (value.data?.csrf_token) csrfToken = value.data.csrf_token
  if (response.status === 401 && path !== '/api/auth/login') {
    csrfToken = ''
    window.dispatchEvent(new Event('campusflow-session-expired'))
  }
  if (!response.ok) throw new Error([value.message || 'Request failed', ...(value.errors || [])].join('\n'))
  if (path === '/api/auth/logout') csrfToken = ''
  return value
}

export async function api<T = any>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const value = await requestJson(`/api/product${path}`, method, body)
  return value.data
}
export async function solvers(): Promise<Row[]> {
  return (await requestJson('/api/solvers')).solvers
}
export function minutes(value: string) { const [h, m] = value.split(':').map(Number); return h * 60 + m }
export function clock(value: number) { return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}` }
export function terminal(state: string) { return !['queued', 'running'].includes(state) }

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { X, AlertCircle, Inbox, LoaderCircle } from 'lucide-react'
import type { Row } from './api'

export function ErrorBox({ error }: { error: string }) { return error ? <div role="alert" className="error"><AlertCircle size={18}/><span>{error}</span></div> : null }
export function Empty({ title, children }: { title: string; children?: ReactNode }) { return <div className="empty"><Inbox size={32}/><h3>{title}</h3><p>{children}</p></div> }
export function Loading() { return <div className="loading" role="status"><LoaderCircle className="spin" size={22}/> Loading your workspace…</div> }
export function Badge({ value }: { value: string }) { return <span className={`badge ${value}`}>{value.replaceAll('_', ' ')}</span> }
export function PageHead({ eyebrow = 'ACADEMIC WORKSPACE', title, description, children }: { eyebrow?: string; title: string; description: string; children?: ReactNode }) {
  return <div className="page-head"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="muted">{description}</p></div><div className="actions">{children}</div></div>
}
export function Modal({ title, children, close }: { title: string; children: ReactNode; close: () => void }) {
  const closeRef = useRef(close)
  closeRef.current = close
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const dialog = document.querySelector('[role="dialog"]') as HTMLElement | null
    const elements = () => Array.from(dialog?.querySelectorAll<HTMLElement>('button,input,select,textarea,[tabindex="0"]') || []).filter(e => !e.hasAttribute('disabled'))
    elements()[0]?.focus()
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeRef.current()
      if (event.key === 'Tab') {
        const items = elements(), first = items[0], last = items.at(-1)
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      }
    }
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('keydown', key); previous?.focus() }
  }, [])
  return <div className="modal-backdrop"><section role="dialog" aria-modal="true" aria-label={title} className="modal"><header><h2>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={close}><X/></button></header>{children}</section></div>
}
export function useLoad<T>(loader: () => Promise<T>, key: string | number = '') {
  const [value, setValue] = useState<T>(), [error, setError] = useState(''), [loading, setLoading] = useState(true)
  useEffect(() => {
    let active = true; setLoading(true); setError('')
    loader().then(v => { if (active) setValue(v) }).catch(e => { if (active) setError(e.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [key])
  return { value, setValue, error, setError, loading }
}
export function VersionSelect({ versions, selected, onChange }: { versions: Row[]; selected: string; onChange: (id: string) => void }) {
  return <label className="select-version">Timetable version<select value={selected} onChange={e => onChange(e.target.value)}><option value="">Choose a timetable</option>{versions.map(v => <option key={v.id} value={v.id}>{v.name} · {v.state}</option>)}</select></label>
}

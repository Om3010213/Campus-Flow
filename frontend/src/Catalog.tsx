import { useState } from 'react'
import { Plus, Search, Pencil, Trash2, Clock3 } from 'lucide-react'
import { api, days, type Catalog, type Row } from './api'
import { Badge, Empty, ErrorBox, Loading, Modal, PageHead, useLoad } from './ui'

const titles: Record<string, string> = { faculty: 'Faculty', subjects: 'Subjects', rooms: 'Classrooms & labs', batches: 'Student batches', requirements: 'Weekly requirements' }
const fields: Record<string, [string, string, string?][]> = {
  faculty: [['id','Faculty ID'],['name','Full name'],['department','Department'],['max_daily_minutes','Maximum daily workload (minutes)','number'],['preferred_start','Preferred start','time'],['preferred_end','Preferred end','time']],
  subjects: [['id','Subject code'],['name','Subject name'],['department','Department'],['semester','Semester','number'],['weekly_sessions','Weekly lecture count','number'],['duration_minutes','Lecture duration (minutes)','number'],['kind','Subject type','kind']],
  rooms: [['id','Room ID'],['name','Room name'],['kind','Room type','kind'],['capacity','Seating capacity','number']],
  batches: [['id','Batch ID'],['department','Department'],['semester','Semester','number'],['division','Division'],['student_count','Student count','number']],
  requirements: [['id','Requirement ID'],['subject_id','Subject','subjects'],['faculty_id','Faculty','faculty'],['batch_id','Batch','batches'],['weekly_sessions','Weekly sessions','number'],['duration_minutes','Duration (minutes)','number']],
}
const defaults: Record<string, Row> = {
  faculty: {id:'',name:'',department:'',subject_ids:[],restricted:false,availability:[],max_daily_minutes:360,preferred_start:'09:00',preferred_end:'16:00'},
  subjects: {id:'',name:'',department:'',semester:1,weekly_sessions:3,duration_minutes:60,kind:'theory'},
  rooms: {id:'',name:'',kind:'theory',capacity:60,restricted:false,availability:[]},
  batches: {id:'',department:'',semester:1,division:'A',student_count:60},
  requirements: {id:'',subject_id:'',faculty_id:'',batch_id:'',weekly_sessions:3,duration_minutes:60},
}

export default function CatalogPage({ kind, embedded = false }: { kind: string; embedded?: boolean }) {
  const [refresh, setRefresh] = useState(0), [query, setQuery] = useState(''), [department, setDepartment] = useState('')
  const state = useLoad(() => api<Catalog>('/catalog'), refresh)
  const [editing, setEditing] = useState<Row | null>(null), [original, setOriginal] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const rows = (state.value?.[kind] || []).filter(row => JSON.stringify(row).toLowerCase().includes(query.toLowerCase()) && (!department || row.department === department))
  function open(row?: Row) { setOriginal(row?.id || ''); setEditing(structuredClone(row || defaults[kind])); setError('') }
  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('')
    try { await api(`/records/${kind}${original ? `/${encodeURIComponent(original)}` : ''}`, original ? 'PUT' : 'POST', editing); setEditing(null); setRefresh(n => n + 1) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function remove(row: Row) {
    if (!confirm(`Delete ${row.name || row.id}? Referenced records cannot be deleted.`)) return
    try { await api(`/records/${kind}/${encodeURIComponent(row.id)}`, 'DELETE'); setRefresh(n => n + 1); setError('') } catch(e) { setError((e as Error).message) }
  }
  const label = (key: string) => fields[kind].find(f => f[0] === key)?.[1] || key
  return <>{!embedded && <PageHead title={titles[kind]} description="A dependable schedule starts with well-organized academic data."/>}<section className="panel"><div className="section-head"><div><h2>{titles[kind]} <span className="count">{state.value?.[kind]?.length || 0}</span></h2><p className="muted">Manage records, assignments, and availability.</p></div><button className="primary" onClick={() => open()}><Plus size={16}/> Add {kind === 'faculty' ? 'faculty' : kind === 'requirements' ? 'requirement' : kind === 'batches' ? 'batch' : kind === 'rooms' ? 'room' : 'subject'}</button></div>
    <div className="filters"><label className="search"><Search size={17}/><input aria-label={`Search ${titles[kind]}`} placeholder={`Search ${titles[kind].toLowerCase()}…`} value={query} onChange={e => setQuery(e.target.value)}/></label>{['faculty','subjects','batches'].includes(kind) && <select aria-label="Department filter" value={department} onChange={e => setDepartment(e.target.value)}><option value="">All departments</option>{[...new Set(state.value?.[kind]?.map(r => r.department))].map(d => <option key={d}>{d}</option>)}</select>}</div>
    <ErrorBox error={state.error || (!editing ? error : '')}/>{state.loading ? <Loading/> : rows.length ? <div className="table-scroll"><table><thead><tr>{fields[kind].filter(([key]) => !['preferred_start','preferred_end'].includes(key)).map(([key]) => <th key={key}>{label(key)}</th>)}<th>Actions</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}>{fields[kind].filter(([key]) => !['preferred_start','preferred_end'].includes(key)).map(([key]) => <td key={key}>{key === 'kind' ? <Badge value={row[key]}/> : key === 'id' ? <span className="code">{row[key]}</span> : row[key]}</td>)}<td><div className="actions"><button className="icon-button" aria-label={`Edit ${row.id}`} onClick={() => open(row)}><Pencil size={16}/></button><button className="icon-button danger" aria-label={`Delete ${row.id}`} onClick={() => remove(row)}><Trash2 size={16}/></button></div></td></tr>)}</tbody></table></div> : <Empty title={query || department ? 'No matching records' : `No ${titles[kind].toLowerCase()} yet`}>Add your first record to get started.</Empty>}</section>
    {editing && <Modal title={`${original ? 'Edit' : 'Add'} ${kind === 'faculty' ? 'faculty member' : titles[kind].toLowerCase()}`} close={() => setEditing(null)}><form onSubmit={save}><ErrorBox error={error}/><div className="form-grid">{fields[kind].map(([key, title, type]) => <label key={key}>{title}{type === 'kind' ? <select value={editing[key]} onChange={e => setEditing({...editing,[key]:e.target.value})}><option value="theory">Theory</option><option value="lab">Laboratory</option></select> : ['faculty','subjects','batches'].includes(type || '') ? <select required value={editing[key]} onChange={e => {
      const next = {...editing,[key]:e.target.value}; if (key === 'subject_id') { const subject = state.value?.subjects.find(s => s.id === e.target.value); if (subject) { next.weekly_sessions=subject.weekly_sessions; next.duration_minutes=subject.duration_minutes } } setEditing(next)
    }}><option value="">Choose {title.toLowerCase()}</option>{state.value?.[type!]?.filter(r => type !== 'faculty' || r.subject_ids.includes(editing.subject_id)).map(r => <option key={r.id} value={r.id}>{r.name ? `${r.name} · ` : ''}{r.id}</option>)}</select> : <input required type={type || 'text'} min={type === 'number' ? 1 : undefined} maxLength={200} disabled={key === 'id' && !!original} value={editing[key]} onChange={e => setEditing({...editing,[key]:type === 'number' ? Number(e.target.value) : e.target.value})}/>}</label>)}</div>
    {kind === 'faculty' && <fieldset><legend>Assigned subjects</legend><div className="check-grid">{state.value?.subjects.map(s => <label key={s.id} className="check"><input type="checkbox" checked={editing.subject_ids.includes(s.id)} onChange={e => setEditing({...editing,subject_ids:e.target.checked ? [...editing.subject_ids,s.id] : editing.subject_ids.filter((id: string) => id !== s.id)})}/>{s.id} · {s.name}</label>)}</div>{!state.value?.subjects.length && <p className="muted">Create subjects first, then assign them here.</p>}</fieldset>}
    {['faculty','rooms'].includes(kind) && <fieldset><legend><Clock3 size={16}/> Availability</legend><label className="check"><input type="checkbox" checked={editing.restricted} onChange={e => setEditing({...editing,restricted:e.target.checked})}/> Restrict availability to the windows below</label><p className="hint">Unchecked means available throughout working hours. Checked with no windows means unavailable.</p>{editing.availability.map((window: Row, i: number) => <div className="window-row" key={i}><select aria-label={`Window ${i+1} day`} value={window.day} onChange={e => setEditing({...editing,availability:editing.availability.map((w: Row,j: number) => i===j ? {...w,day:e.target.value} : w)})}>{days.map(d => <option key={d}>{d}</option>)}</select>{['start','end'].map(key => <input key={key} aria-label={`Window ${i+1} ${key}`} type="time" required value={window[key]} onChange={e => setEditing({...editing,availability:editing.availability.map((w: Row,j: number) => i===j ? {...w,[key]:e.target.value} : w)})}/>)}<button type="button" aria-label={`Remove window ${i+1}`} className="icon-button danger" onClick={() => setEditing({...editing,availability:editing.availability.filter((_: Row,j: number) => j!==i)})}><Trash2 size={16}/></button></div>)}<button type="button" onClick={() => setEditing({...editing,availability:[...editing.availability,{day:'Monday',start:'09:00',end:'16:00'}]})}><Plus size={15}/> Add availability window</button></fieldset>}
    <div className="modal-actions"><button type="button" onClick={() => setEditing(null)}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save record'}</button></div></form></Modal>}
  </>
}

import { useState } from 'react'
import { NavLink, Routes, Route, useLocation, Link } from 'react-router-dom'
import { LayoutDashboard, UsersRound, BookOpen, Building2, GraduationCap, SlidersHorizontal, Sparkles, CalendarDays, RefreshCw, ChartNoAxesCombined, Settings2, Menu, ArrowUpRight, Layers3, Moon, Sun } from 'lucide-react'
import Dashboard from './Dashboard'
import CatalogPage from './Catalog'
import Configuration from './Configuration'
import Generation from './Generation'
import Timetable from './Timetable'
import Reports from './Reports'
import { ErrorBox, PageHead, useLoad } from './ui'
import { api } from './api'

const navigation = [
  ['/', 'Overview', LayoutDashboard], ['/faculty', 'Faculty', UsersRound], ['/subjects', 'Subjects', BookOpen],
  ['/rooms', 'Classrooms & labs', Building2], ['/batches', 'Student batches', GraduationCap],
  ['/configuration', 'Academic configuration', SlidersHorizontal], ['/generate', 'Generate timetable', Sparkles],
  ['/timetables', 'Timetable viewer', CalendarDays], ['/rescheduling', 'Rescheduling', RefreshCw],
  ['/reports', 'Reports & exports', ChartNoAxesCombined], ['/settings', 'Settings', Settings2],
] as const

export default function App() {
  const [menu, setMenu] = useState(false)
  const [dark, setDark] = useState(localStorage.getItem('campusflow-theme') === 'dark')
  const location = useLocation()
  function theme() { const next = !dark; setDark(next); localStorage.setItem('campusflow-theme', next ? 'dark' : 'light') }
  return <div className={`app ${dark ? 'dark' : ''}`}>
    <aside className={`sidebar ${menu ? 'open' : ''}`}>
      <Link to="/" className="brand"><span className="brand-icon"><Layers3 size={23}/></span><span>Campus<span className="brand-flow">Flow</span><small>ACADEMIC OPERATIONS</small></span></Link>
      <div className="workspace-label"><span className="avatar">CF</span><div>College workspace<small>Local administration</small></div><span className="online-dot"/></div>
      <p className="nav-label">WORKSPACE</p>
      <nav>{navigation.map(([path, label, Icon], i) => <div key={path}>{i === 6 && <p className="nav-label">SCHEDULING & INSIGHTS</p>}<NavLink end={path === '/'} to={path} onClick={() => setMenu(false)}><Icon size={18}/><span>{label}</span>{path === '/generate' && <span className="nav-new" aria-hidden="true">GO</span>}</NavLink></div>)}</nav>
      <div className="sidebar-footer"><div className="online-dot"/><span>Built for your campus<small>Private · local workspace</small></span></div>
    </aside>
    {menu && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMenu(false)}/>}
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMenu(!menu)}><Menu/></button><span>Workspace</span><span>/</span><strong>{navigation.find(([path]) => path === location.pathname)?.[1] || 'Timetables'}</strong></div><div className="top-actions"><span className="local-pill"><span className="online-dot"/> Local workspace</span><button className="icon-button" aria-label="Toggle theme" onClick={theme}>{dark ? <Sun size={18}/> : <Moon size={18}/>}</button><span className="avatar admin">AD</span></div></header>
      <main><Routes><Route path="/" element={<Dashboard/>}/>{['faculty','subjects','rooms','batches'].map(kind => <Route key={kind} path={`/${kind}`} element={<CatalogPage key={kind} kind={kind}/>}/>)}<Route path="/configuration" element={<Configuration/>}/><Route path="/generate" element={<Generation/>}/><Route path="/timetables" element={<Timetable/>}/><Route path="/rescheduling" element={<Generation rescheduling/>}/><Route path="/reports" element={<Reports/>}/><Route path="/settings" element={<Settings dark={dark} theme={theme}/>}/><Route path="*" element={<PageHead title="Page not found" description="Use the workspace navigation to continue."/>}/></Routes></main>
      <footer className="page-footer">CampusFlow <span>Thoughtfully scheduled. Better connected.</span><a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">API documentation <ArrowUpRight size={13}/></a></footer>
    </div>
  </div>
}

function Settings({ dark, theme }: { dark: boolean; theme: () => void }) {
  const { value, error } = useLoad(() => api('/settings'))
  const [seedMessage, setSeedMessage] = useState('')
  return <><PageHead title="Workspace settings" description="Make this local workspace your own."/><ErrorBox error={error}/><section className="panel settings-panel"><h2>Appearance</h2><p className="muted">Your preference is saved on this device.</p><button onClick={theme}>{dark ? 'Switch to light theme' : 'Switch to dark theme'}</button><hr/><h2>Connection & storage</h2><p>{value ? 'Backend connected. SQLite persistence is available.' : 'Checking backend connection…'}</p><p className="muted">Data stays in your local CampusFlow database. Stop the backend before copying data/campusflow.db for a backup.</p><a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">Open API documentation ↗</a><hr/><h2>Explore a fictional college</h2><p className="muted">Load faculty, rooms, subjects, batches, and requirements into an empty catalog. Existing data is never overwritten. Timetables must still be generated.</p><button onClick={async()=>{try{await api('/seed','POST');setSeedMessage('Demo catalog loaded. Open Overview or Generate Timetable to continue.')}catch(e){setSeedMessage((e as Error).message)}}}>Load demo catalog</button>{seedMessage&&<p role="status">{seedMessage}</p>}<hr/><h2>Scheduling limits</h2><p className="muted">Up to 500 requested sessions, 30 seconds of solver time, and two concurrent background jobs. Large datasets can time out; a timeout does not mean the timetable is impossible.</p></section></>
}

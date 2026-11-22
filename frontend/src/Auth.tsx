import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { loadSession, requestJson, type Row } from './api'
import { ErrorBox, Loading } from './ui'
import { useLocation, useNavigate, Navigate } from 'react-router-dom'
import Onboarding, { AuthNavigation, WorkspaceOnboarding } from './Onboarding'

type AuthState = { user: Row | null; setUser: (user: Row | null) => void; logout: () => Promise<void> }
const AuthContext = createContext<AuthState>({user:null,setUser:()=>{},logout:async()=>{}})
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({children}:{children:ReactNode}) {
  const location=useLocation(),navigate=useNavigate()
  const [user,setUser]=useState<Row|null>(null), [loading,setLoading]=useState(true), [error,setError]=useState('')
  useEffect(()=>{
    loadSession().then(result=>setUser(result.data.user)).catch(e=>setError(e.message)).finally(()=>setLoading(false))
    const expired=()=>{setUser(null);setError('Your session expired or was revoked. Please sign in again.')}
    window.addEventListener('campusflow-session-expired',expired)
    return()=>window.removeEventListener('campusflow-session-expired',expired)
  },[])
  async function logout(){await requestJson('/api/auth/logout','POST');setUser(null);setError('');navigate('/sign-in',{replace:true})}
  return <AuthContext.Provider value={{user,setUser,logout}}>{loading?<Loading/>:location.pathname==='/accept-invitation'?<Onboarding key={location.pathname}/>:location.pathname==='/verify-email'?<Navigate to="/sign-in" replace/>:!user?(location.pathname==='/sign-up'?<Onboarding/>:<Login notice={error} success={location.state?.notice||''}/>):['/sign-up','/sign-in'].includes(location.pathname)?<Navigate to="/" replace/>:user.must_change_password?<div className="login-shell"><PasswordForm required/></div>:user.role==='unassigned'?<WorkspaceOnboarding/>:children}</AuthContext.Provider>
}

function Login({notice,success}:{notice:string;success:string}) {
  const navigate=useNavigate(),{setUser}=useAuth(), [username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false)
  async function submit(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const result=await requestJson('/api/auth/login','POST',{username,password});setPassword('');setUser(result.data.user);navigate('/',{replace:true})}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <div className="login-shell"><form className="panel login-panel" onSubmit={submit}><AuthNavigation/><p className="eyebrow">CAMPUSFLOW · SECURE WORKSPACE</p><h1>Welcome back.</h1><p className="muted">Sign in to your academic workspace.</p><ErrorBox error={error||notice}/>{success&&<p role="status">{success}</p>}<label>Email<input required autoComplete="username" maxLength={254} value={username} onChange={e=>setUsername(e.target.value)}/></label><label>Password<input required type="password" autoComplete="current-password" maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/></label><button className="primary full" disabled={busy}>{busy?'Signing in…':'Sign in'}</button><p className="hint">Existing institution accounts are provisioned by your administrator. Sign up with your email and password, then create a School or College workspace. For password recovery, contact your administrator.</p></form></div>
}

export function PasswordForm({required=false}:{required?:boolean}){
  const {setUser,logout}=useAuth(),[current,setCurrent]=useState(''),[next,setNext]=useState(''),[confirm,setConfirm]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false)
  async function submit(e:React.FormEvent){e.preventDefault();setError('');setMessage('');if(next!==confirm){setError('New passwords do not match.');return}setBusy(true);try{const result=await requestJson('/api/auth/password','POST',{current_password:current,new_password:next});setUser(result.data.user);setCurrent('');setNext('');setConfirm('');setMessage('Password changed. Other sessions have been revoked.')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <form className="panel login-panel" onSubmit={submit}><h2>{required?'Change your temporary password':'Change password'}</h2><p className="muted">Use a unique passphrase of 12–128 characters.</p><ErrorBox error={error}/><label>Current password<input required type="password" autoComplete="current-password" value={current} onChange={e=>setCurrent(e.target.value)}/></label><label>New password<input required minLength={12} maxLength={128} type="password" autoComplete="new-password" value={next} onChange={e=>setNext(e.target.value)}/></label><label>Confirm new password<input required type="password" autoComplete="new-password" value={confirm} onChange={e=>setConfirm(e.target.value)}/></label><button className="primary" disabled={busy}>Change password</button>{required&&<button type="button" onClick={()=>logout().catch(e=>setError(e.message))}>Sign out</button>}{message&&<p role="status">{message}</p>}</form>
}

export function RoleGate({roles,children}:{roles:string[];children:ReactNode}){
  const {user}=useAuth()
  return user && roles.includes(user.role)?<>{children}</>:<ErrorBox error="You do not have permission to access this page."/>
}

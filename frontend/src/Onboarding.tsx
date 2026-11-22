import {useEffect,useState} from 'react'
import {Link,useLocation,useNavigate} from 'react-router-dom'
import {requestJson} from './api'
import {useAuth} from './Auth'
import {ErrorBox} from './ui'
export function AuthNavigation(){return <nav aria-label="Account navigation"><Link to="/sign-in">Sign In</Link><span> · </span><Link to="/sign-up">Sign Up</Link></nav>}
export default function Onboarding(){
 const location=useLocation(),navigate=useNavigate(),{setUser}=useAuth(),invitation=location.pathname==='/accept-invitation'
 const [token]=useState(()=>new URLSearchParams(location.hash.slice(1)).get('token')||'')
 const [enabled,setEnabled]=useState(invitation),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('')
 const [form,setForm]=useState({name:'',email:'',password:''})
 useEffect(()=>{if(location.hash)navigate(location.pathname,{replace:true});if(!invitation)requestJson('/api/onboarding/status').then(r=>setEnabled(r.data.registration_enabled)).catch(e=>setError(e.message))},[])
 async function submit(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{
  const result=await requestJson('/api/onboarding/'+(invitation?'accept-invitation':'register'),'POST',invitation?{token,password:form.password}:form)
  setForm({...form,password:''});setMessage(result.message)
  if(invitation){setUser(null);setEnabled(false)}else navigate('/sign-in',{replace:true,state:{notice:result.message}})
 }catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <div className="login-shell"><form className="panel login-panel" onSubmit={submit}><AuthNavigation/><h1>{invitation?'Accept your invitation':'Create your account'}</h1><p>{invitation?'Choose a password for a new account, or enter your current password if already signed in.':'Sign up with your name, email and password. After signing in, create a School or College workspace or accept an invitation.'}</p><ErrorBox error={error}/>{message&&<p role="status">{message}</p>}{!invitation&&<><label>Name<input required autoComplete="name" maxLength={120} value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label><label>Email<input required type="email" autoComplete="email" maxLength={254} value={form.email} onChange={e=>setForm({...form,email:e.target.value})}/></label></>}<label>Password<input required type="password" minLength={12} maxLength={128} autoComplete="new-password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/></label><button className="primary full" disabled={!enabled||busy||(invitation&&!token)}>{busy?'Submitting…':invitation?'Accept invitation':'Sign up'}</button>{!enabled&&!invitation&&<p>Registration is currently disabled.</p>}{invitation&&!token&&<p role="alert">Open the complete invitation link shared by your administrator.</p>}</form></div>
}

export function WorkspaceOnboarding(){
 const {setUser,logout}=useAuth(),navigate=useNavigate()
 const [name,setName]=useState(''),[kind,setKind]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 async function submit(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const r=await requestJson('/api/onboarding/workspace','POST',{institution_name:name,institution_type:kind});setUser(r.data.user);navigate('/',{replace:true})}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <main className="login-shell"><form className="panel login-panel" onSubmit={submit}><h1>Welcome to CampusFlow</h1><p>Your account is ready. Create a new institution workspace to manage your own School or College. To join an existing institution, use its administrator's private invitation link.</p><ErrorBox error={error}/><label>Institution Type<select required value={kind} onChange={e=>setKind(e.target.value)}><option value="">Choose institution type</option><option value="SCHOOL">School</option><option value="COLLEGE">College</option></select></label><label>Institution Name<input required maxLength={200} value={name} onChange={e=>setName(e.target.value)}/></label><p>Creating a workspace makes you administrator of that new institution only.</p><button className="primary" disabled={busy}>Create workspace</button><button type="button" onClick={()=>logout().catch(e=>setError(e.message))}>Sign out</button></form></main>
}

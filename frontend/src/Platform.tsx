import {useState} from 'react'
import {requestJson,type Row} from './api'
import {useAuth,PasswordForm} from './Auth'
import {ErrorBox,useLoad} from './ui'
export default function Platform(){
 const {logout,user}=useAuth(),[refresh,setRefresh]=useState(0),[error,setError]=useState('')
 const state=useLoad(async()=>(await requestJson('/api/platform/institutions')).data as Row[],refresh)
 return <main><h1>Institution directory</h1><p>Platform operators manage institution status. Academic data is restricted to institution memberships.</p><ErrorBox error={error||state.error}/><button onClick={()=>logout().catch(e=>setError(e.message))}>Sign out</button><table><thead><tr><th>Institution</th><th>Type</th><th>Status</th><th>Action</th></tr></thead><tbody>{state.value?.map(r=><tr key={r.institution_id}><td>{r.institution_name}</td><td>{r.institution_type}</td><td>{r.status}</td><td>{r.institution_id!==user?.institution_id&&<button onClick={async()=>{if(!confirm('Change this institution status? Existing sessions will be revoked.'))return;try{await requestJson('/api/platform/institutions/'+r.institution_id+'/status','PUT',{status:r.status==='ACTIVE'?'SUSPENDED':'ACTIVE'});setRefresh(n=>n+1)}catch(e){setError((e as Error).message)}}}>{r.status==='ACTIVE'?'Suspend':'Activate'}</button>}</td></tr>)}</tbody></table><PasswordForm/></main>
}

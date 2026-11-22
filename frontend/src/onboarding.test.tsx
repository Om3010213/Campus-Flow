import {beforeEach,expect,it,vi} from 'vitest'
import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {MemoryRouter,useLocation} from 'react-router-dom'
import App from './App'
function response(data:unknown,status=200){return Promise.resolve({ok:status<400,status,json:()=>Promise.resolve(data)})}
function setup(path='/',enabled=true,user:unknown=null){
 const fetch=vi.fn((url:string,init?:RequestInit)=>{
  if(url==='/api/auth/session')return response({data:{user,csrf_token:'csrf-test'}})
  if(url==='/api/onboarding/status')return response({data:{registration_enabled:enabled}})
  if(url==='/api/onboarding/register')return response({status:'registered',message:'Account created. Sign in.'},201)
  return response({data:[]})
 })
 vi.stubGlobal('fetch',fetch)
 function Location(){const value=useLocation();return <div aria-label="Current route">{value.pathname+value.hash}</div>}
 render(<MemoryRouter initialEntries={[path]}><App/><Location/></MemoryRouter>);return fetch
}
beforeEach(()=>vi.restoreAllMocks())
it('navigates between password sign in and sign up',async()=>{
 setup();fireEvent.click(await screen.findByRole('link',{name:'Sign Up'}))
 expect(await screen.findByRole('heading',{name:'Create your account'})).toBeInTheDocument()
 fireEvent.click(screen.getByRole('link',{name:'Sign In'}))
 expect(await screen.findByRole('heading',{name:'Welcome back.'})).toBeInTheDocument()
})
it('submits only name email password with CSRF then redirects to login',async()=>{
 const fetch=setup('/sign-up')
 fireEvent.change(await screen.findByLabelText('Name'),{target:{value:'Asha Rao'}})
 fireEvent.change(screen.getByLabelText('Email'),{target:{value:'asha@north.example'}})
 fireEvent.change(screen.getByLabelText('Password'),{target:{value:'A strong test passphrase!'}})
 await waitFor(()=>expect(screen.getByRole('button',{name:'Sign up'})).toBeEnabled())
 fireEvent.click(screen.getByRole('button',{name:'Sign up'}))
 expect(await screen.findByRole('heading',{name:'Welcome back.'})).toBeInTheDocument()
 const call=fetch.mock.calls.find(([url])=>url==='/api/onboarding/register')![1]!
 expect(call.headers).toMatchObject({'X-CSRF-Token':'csrf-test'})
 expect(Object.keys(JSON.parse(call.body as string)).sort()).toEqual(['email','name','password'])
 expect(screen.getByLabelText('Current route')).toHaveTextContent('/sign-in')
 expect(fetch.mock.calls.some(([url])=>url.includes('verify')||url.includes('resend'))).toBe(false)
})
it('retired verification links redirect to login without granting access',async()=>{
 const fetch=setup('/verify-email#token='+'a'.repeat(43))
 await screen.findByRole('heading',{name:'Welcome back.'})
 await waitFor(()=>expect(screen.getByLabelText('Current route')).toHaveTextContent(/^\/sign-in$/))
 expect(fetch.mock.calls.some(([url])=>url==='/api/onboarding/verify')).toBe(false)
})
it('honors the registration gate',async()=>{
 setup('/sign-up',false)
 expect(await screen.findByRole('button',{name:'Sign up'})).toBeDisabled()
})
it('signed in accounts leave signup and see onboarding without administrator controls',async()=>{
 setup('/sign-up',true,{id:'new',username:'new@example.test',role:'unassigned',institution_id:null})
 expect(await screen.findByRole('heading',{name:'Welcome to CampusFlow'})).toBeInTheDocument()
 expect(screen.getByLabelText('Current route')).toHaveTextContent(/^\/$/)
 expect(screen.queryByRole('link',{name:'Users & access'})).not.toBeInTheDocument()
 expect(screen.getByRole('button',{name:'Create workspace'})).toBeInTheDocument()
})

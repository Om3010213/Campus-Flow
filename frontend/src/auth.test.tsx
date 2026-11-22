import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from './App'
import { requestJson } from './api'

const viewer = {username:'reader',role:'viewer',must_change_password:false}
function response(data: unknown, status=200) {return Promise.resolve({ok:status<400,status,json:()=>Promise.resolve(data)})}
function mockSession(user: unknown=null) {
  return vi.fn((path:string, init?:RequestInit):Promise<any>=>{
    if(path==='/api/auth/session')return response({data:{user,csrf_token:'bootstrap-token'}})
    if(path==='/api/auth/login')return response({data:{user:viewer,csrf_token:'rotated-token'}})
    if(path==='/api/auth/logout')return response({data:null})
    return response({data:[]})
  })
}
beforeEach(()=>{vi.restoreAllMocks();localStorage.clear()})

it('requires login, sends CSRF, and logs out',async()=>{
  const fetch=mockSession();vi.stubGlobal('fetch',fetch)
  render(<MemoryRouter initialEntries={['/settings']}><App/></MemoryRouter>)
  fireEvent.change(await screen.findByLabelText('Email'),{target:{value:'reader'}})
  fireEvent.change(screen.getByLabelText('Password'),{target:{value:'A long passphrase!'}})
  fireEvent.click(screen.getByRole('button',{name:'Sign in'}))
  expect(await screen.findByRole('button',{name:'Sign out'})).toBeInTheDocument()
  const login=fetch.mock.calls.find(([path])=>path==='/api/auth/login')!
  expect(login[1]?.credentials).toBe('same-origin')
  expect(login[1]?.headers).toMatchObject({'X-CSRF-Token':'bootstrap-token'})
  fireEvent.click(screen.getByRole('button',{name:'Sign out'}))
  expect(await screen.findByRole('button',{name:'Sign in'})).toBeInTheDocument()
  expect(fetch.mock.calls.find(([path])=>path==='/api/auth/logout')![1]?.headers).toMatchObject({'X-CSRF-Token':'rotated-token'})
})

it('hides administrator controls and guards direct viewer navigation',async()=>{
  vi.stubGlobal('fetch',mockSession(viewer))
  render(<MemoryRouter initialEntries={['/users']}><App/></MemoryRouter>)
  expect(await screen.findByRole('alert')).toHaveTextContent('permission')
  expect(screen.queryByRole('link',{name:'Users & access'})).not.toBeInTheDocument()
  expect(screen.queryByRole('link',{name:'Faculty'})).not.toBeInTheDocument()
  expect(screen.queryByRole('link',{name:'Generate timetable'})).not.toBeInTheDocument()
})

it('returns to login when a session is revoked',async()=>{
  const fetch=mockSession(viewer);vi.stubGlobal('fetch',fetch)
  render(<MemoryRouter initialEntries={['/settings']}><App/></MemoryRouter>)
  await screen.findByRole('heading',{name:'Workspace settings'})
  fetch.mockImplementationOnce(()=>response({message:'Authentication required'},401))
  await expect(requestJson('/api/product/versions')).rejects.toThrow('Authentication required')
  expect(await screen.findByRole('button',{name:'Sign in'})).toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('expired or was revoked')
})

it('shows login failure without opening protected content',async()=>{
  const fetch=mockSession();vi.stubGlobal('fetch',fetch)
  render(<MemoryRouter><App/></MemoryRouter>)
  fireEvent.change(await screen.findByLabelText('Email'),{target:{value:'reader'}})
  fireEvent.change(screen.getByLabelText('Password'),{target:{value:'wrong'}})
  fetch.mockImplementationOnce(()=>response({message:'Invalid username or password.'},401))
  fireEvent.click(screen.getByRole('button',{name:'Sign in'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password')
  await waitFor(()=>expect(screen.getByRole('button',{name:'Sign in'})).toBeEnabled())
  expect(screen.queryByRole('button',{name:'Sign out'})).not.toBeInTheDocument()
})

it('requires temporary password replacement before opening the workspace',async()=>{
  vi.stubGlobal('fetch',mockSession({...viewer,must_change_password:true}))
  render(<MemoryRouter><App/></MemoryRouter>)
  expect(await screen.findByRole('heading',{name:'Change your temporary password'})).toBeInTheDocument()
  expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
})

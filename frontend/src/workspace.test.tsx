import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from './App'
import CatalogPage from './Catalog'
import Generation from './Generation'
import { WeeklyGrid } from './Timetable'

const catalog = {faculty:[],subjects:[],rooms:[],batches:[],requirements:[]}
function response(data: unknown, ok=true) {return Promise.resolve({ok,json:()=>Promise.resolve(data)})}
beforeEach(()=>{localStorage.clear();vi.restoreAllMocks();vi.stubGlobal('fetch',vi.fn((path: string)=>response(path==='/api/auth/session'?{data:{user:{username:'admin',role:'administrator'},csrf_token:'test-csrf'}}:path==='/api/solvers'?{solvers:[{name:'csp',available:true}]}:{data:path.includes('catalog')?catalog:path.includes('settings')?{}:[]})))})

describe('workspace components',()=>{
  it('navigates and shows real empty catalog states',async()=>{
    render(<MemoryRouter><App/></MemoryRouter>)
    expect(await screen.findByText('Your first timetable is waiting')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'Faculty' }))
    expect(await screen.findByText('No faculty yet')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Toggle theme'}))
    expect(localStorage.getItem('campusflow-theme')).toBe('dark')
  })
  it('loads records and reports API failure without losing the form',async()=>{
    vi.stubGlobal('fetch',vi.fn((_path: string, init?: RequestInit)=>init?.method==='POST'?response({message:'Duplicate identifier'},false):response({data:catalog})))
    render(<CatalogPage kind="rooms"/>)
    await screen.findByText('No classrooms & labs yet')
    fireEvent.click(screen.getByRole('button',{name:'Add room'}))
    fireEvent.change(screen.getByLabelText('Room ID'),{target:{value:'C101'}})
    fireEvent.change(screen.getByLabelText('Room name'),{target:{value:'Classroom 101'}})
    fireEvent.click(screen.getByRole('button',{name:'Save record'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('Duplicate identifier')
    expect(screen.getByLabelText('Room name')).toHaveValue('Classroom 101')
  })
  it('shows loading and network errors',async()=>{
    vi.stubGlobal('fetch',vi.fn(()=>Promise.reject(new Error('Backend is offline'))))
    render(<CatalogPage kind="subjects"/>)
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend is offline')
  })
  it('renders weekly intervals and lab duration',()=>{
    const select=vi.fn()
    render(<WeeklyGrid lectures={[{id:'LAB:1',subject:'LAB',faculty:'F1',batch:'B1',classroom:'L1',day:'Monday',start:'09:00',end:'11:00'}]} policy={{subjects:[{id:'LAB',name:'Database Lab',kind:'lab'}],faculty:[{id:'F1',name:'Dr Rao'}]}} onSelect={select}/>)
    expect(screen.getByText('09:00–11:00 · LAB')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Session LAB:1'}))
    expect(select).toHaveBeenCalledOnce()
  })
  it('starts generation and displays the validated result',async()=>{
    vi.stubGlobal('fetch',vi.fn((path: string, init?: RequestInit)=>{
      if(path==='/api/solvers')return response({solvers:[{name:'csp',available:true}]})
      if(path==='/api/product/jobs'&&init?.method==='POST')return response({data:{id:'job1'}})
      if(path==='/api/product/jobs/job1')return response({data:{id:'job1',state:'success',solver:'csp',duration_seconds:1,result:{lectures:[],validation:{valid:true}}}})
      return response({data:[]})
    }))
    render(<MemoryRouter><Generation/></MemoryRouter>)
    fireEvent.click(screen.getByRole('button',{name:'Generate timetable'}))
    expect(await screen.findByText('A complete schedule is ready.')).toBeInTheDocument()
    expect(screen.getByText('Passed independent validation')).toBeInTheDocument()
    await waitFor(()=>expect(screen.getByRole('button',{name:'Save as a new version'})).toBeEnabled())
  })
})

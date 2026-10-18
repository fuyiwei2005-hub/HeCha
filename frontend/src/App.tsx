import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchMe, friendly, logout, SessionExpiredError } from './api'
import { AppLayout } from './components/AppLayout'
import { LoginPage } from './components/LoginPage'
import { Lightbox } from './components/Lightbox'
import { Toaster, useToasts } from './components/Toaster'
import { HomePage } from './pages/HomePage'
import { DetectPage } from './pages/DetectPage'
import { RecordsPage } from './pages/RecordsPage'
import { StatisticsPage } from './pages/StatisticsPage'
import { InformationPage } from './pages/InformationPage'
import { safeReturnPath } from './routing'
export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('token') || '')
  const [zoom, setZoom] = useState<{url: string; caption: string} | null>(null)
  const [leaving, setLeaving] = useState(false)
  const client = useQueryClient(), location = useLocation(), navigate = useNavigate(), toasts = useToasts()
  const me = useQuery({queryKey: ['me',token], queryFn: fetchMe, enabled: !!token, staleTime: 60000})
  const expire = useCallback(() => {localStorage.removeItem('token'); setToken(''); setZoom(null); client.clear()}, [client])
  const onError = useCallback((error: unknown) => {
    if (error instanceof SessionExpiredError) expire()
    else toasts.error(friendly(error))
  }, [expire, toasts.error])
  useEffect(() => {if (me.error instanceof SessionExpiredError) expire()}, [me.error, expire])
  useEffect(() => {
    const sync = (event: StorageEvent) => {if (event.key === 'token') {client.clear(); setToken(event.newValue || ''); setZoom(null)}}
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [client])
  async function leave() {if (leaving) return; setLeaving(true); await logout(); expire(); setLeaving(false)}
  const next = safeReturnPath(new URLSearchParams(location.search).get('next'))
  if (!token) {
    if (location.pathname !== '/login') return <Navigate replace to={'/login?next='+encodeURIComponent(safeReturnPath(location.pathname))}/>
    return <LoginPage onAuthed={() => {client.clear(); setToken(localStorage.getItem('token') || '')}}/>
  }
  if (me.isPending) return <div className="session-loading" role="status">正在验证登录…</div>
  if (me.error) return <div className="session-loading"><p className="alert alert-error">暂时无法验证登录，请检查连接后重试。</p><button className="btn" onClick={() => void me.refetch()}>重试连接</button><button className="btn btn-ghost" onClick={expire}>重新登录</button></div>
  if (location.pathname === '/login') return <Navigate replace to={next}/>
  return <><Toaster items={toasts.items} onDismiss={toasts.dismiss}/>
    <Routes><Route element={<AppLayout username={me.data?.username || me.data?.email || '已登录'} onLogout={() => void leave()} context={{onError, notify: toasts.success, onZoom: (url,caption) => setZoom({url,caption})}}/>}>
      <Route index element={<HomePage/>}/>
      <Route path="detect" element={<DetectPage key="image" media="image"/>}/>
      <Route path="video" element={<DetectPage key="video" media="video"/>}/>
      <Route path="history" element={<RecordsPage/>}/>
      <Route path="statistics" element={<StatisticsPage/>}/>
      {['features','about','deployment'].map(page => <Route key={page} path={page} element={<InformationPage key={page} page={page}/>}/>)}
      <Route path="model" element={<Navigate replace to="/"/>}/>
      <Route path="contact" element={<Navigate replace to="/#contact"/>}/>
      <Route path="*" element={<section className="empty"><h2>页面不存在</h2><button className="btn" onClick={() => navigate('/')}>返回首页</button></section>}/>
    </Route></Routes>
    {zoom && <Lightbox {...zoom} onClose={() => setZoom(null)}/>}
  </>
}

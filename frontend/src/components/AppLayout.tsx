import { TaskNotifications } from './TaskNotifications'
import { ContactFooter } from './ContactFooter'
import { usePageMotion } from '../hooks/usePageMotion'
import { Icon, BrandMark } from './Icon'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '../api'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { modules } from '../routing'
export type PageContext = { onError: (error: unknown) => void; notify: (text: string) => void; onZoom: (url: string, caption: string) => void }
export function AppLayout({username, onLogout, context}: {username: string; onLogout: () => void; context: PageContext}) {
  const [open, setOpen] = useState(false)
  const toggle = useRef<HTMLButtonElement>(null), menu = useRef<HTMLElement>(null), content = useRef<HTMLDivElement>(null)
  const drawer = useRef<HTMLElement>(null), stage = useRef<HTMLDivElement>(null), transition = useRef<Animation | null>(null)
  const location = useLocation()
  usePageMotion(location.pathname)
  useLayoutEffect(() => { setOpen(false); if (location.hash !== '#contact') window.scrollTo({top:0,left:0,behavior:'instant'}); document.title = (modules.find(([path]) => path === location.pathname)?.[1] || '页面') + ' · 禾察' }, [location.pathname])
  useLayoutEffect(() => {
    transition.current?.cancel()
    if (!stage.current || matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const animation=stage.current.animate([{opacity:.15,transform:'translate3d(0,12px,0)'},{opacity:1,transform:'translate3d(0,0,0)'}],{duration:460,easing:'cubic-bezier(.16,1,.3,1)'})
    transition.current=animation
    const preference=matchMedia('(prefers-reduced-motion: reduce)')
    const stop=()=>{if(preference.matches)animation.cancel()}
    preference.addEventListener('change',stop)
    return ()=>{animation.cancel();preference.removeEventListener('change',stop)}
  },[location.pathname,location.search])
  useEffect(() => {
    drawer.current?.toggleAttribute('inert',!open)
  },[open])
  useEffect(() => {
    if (location.pathname !== '/' || location.hash !== '#contact') return
    const frame=requestAnimationFrame(()=>document.getElementById('contact')?.scrollIntoView({behavior:'instant',block:'start'}))
    return ()=>cancelAnimationFrame(frame)
  },[location.pathname,location.hash])
  useEffect(() => {
    content.current?.toggleAttribute('inert', open)
    if (!open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); toggle.current?.focus() }
      if (event.key === 'Tab') {
        const links = menu.current?.querySelectorAll<HTMLAnchorElement>('a')
        const last = links?.[links.length - 1]
        if (event.shiftKey && document.activeElement === toggle.current) {event.preventDefault(); last?.focus()}
        else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); toggle.current?.focus()}
      }
    }
    document.addEventListener('keydown', key)
    return () => {document.body.style.overflow = previous; document.removeEventListener('keydown', key); content.current?.removeAttribute('inert')}
  }, [open])
  const health = useQuery({queryKey: ['health'], queryFn: fetchHealth, staleTime: 60000})
  const title = modules.find(([path]) => path === location.pathname)?.[1] || '页面'
  return <>
    <div className={'drawer-layer'+(open ? ' is-open' : '')} role={open ? 'dialog' : undefined} aria-modal={open ? true : undefined} aria-label={open ? '功能导航' : undefined}>
      <button className="drawer-backdrop" aria-label="关闭功能菜单" tabIndex={-1} aria-hidden={!open} disabled={!open} onClick={() => {setOpen(false); toggle.current?.focus()}} />
      <button ref={toggle} id="menuToggle" className="btn drawer-trigger" aria-label={open ? '收起功能菜单' : '展开功能菜单'} aria-expanded={open} aria-controls="moduleDrawer" onClick={() => setOpen(value=>!value)}><span className="menu-line"/><span className="menu-line"/><span className="menu-line"/></button>
      <aside ref={drawer} id="moduleDrawer" className={'module-drawer'+(open ? ' open' : '')} aria-hidden={!open}>
        <div className="drawer-header"><h2>功能导航</h2><span>HECHA WORKSPACE</span></div>
        <nav ref={menu} id="moduleNav" aria-label="功能导航" style={{gridTemplateRows:`repeat(${modules.length},minmax(44px,1fr))`}}>{modules.map(([path, label], index) => <NavLink key={path} to={path} end onClick={() => {setOpen(false); toggle.current?.focus()}}><Icon index={index}/><span>{label}</span><span className="drawer-link-arrow" aria-hidden="true">↗</span></NavLink>)}</nav>
        <div className="drawer-footer"><BrandMark/><div><strong>禾察</strong><span>观察细微 · 守护生长</span></div></div>
      </aside>
    </div>
    <div ref={content} className={"product-content" + (location.pathname === '/' ? ' page-home' : '')}>
      <header className="topbar"><div className="topbar-inner">
        <NavLink className="brand" to="/"><span className="brand-mark"><BrandMark/></span><span className="brand-text"><strong>禾察</strong><span>智能植保决策平台</span></span></NavLink>
        <div className="topbar-right">{location.pathname==='/'&&<Link className="btn btn-sm direct-recognition" to="/detect">直接识别</Link>}<span className="account-name">{username}</span><button className="btn btn-sm btn-ghost" onClick={onLogout}>退出登录</button></div>
      </div></header>
      <div ref={stage} className="route-stage"><main className="shell"><div className="route-heading">{location.pathname!=='/'&&<nav className="page-breadcrumb" aria-label="当前位置"><Link to="/">首页</Link><span aria-hidden="true">/</span><span aria-current="page">{title}</span></nav>}<p className="page-kicker">禾察 · 让田间观察更清晰</p><h1>{title}</h1></div>{health.data?.detector === 'mock' && <p className="alert alert-warn" role="status">当前为演示模式，仅验证功能流程，未启用真实识别模型。</p>}
      {health.data?.detector === 'unavailable' && <p className="alert alert-error" role="status">识别模型暂不可用，请检查模型配置后再上传。</p>}
      <TaskNotifications onError={context.onError}/><Outlet context={context}/></main>
      {location.pathname === '/' ? <ContactFooter/> : <footer className="product-footer"><span>禾察 · 农作物害虫智能识别与植保决策平台</span><Link to="/#contact">联系我们 ↗</Link></footer>}</div>
    </div>
  </>
}

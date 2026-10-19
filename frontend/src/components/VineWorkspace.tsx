import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { modules } from '../routing'
import { Icon } from './Icon'
import { FieldPest } from './FieldPest'

const pests=['蚜虫','稻飞虱','棉铃虫','白粉虱','蝗虫','蓟马']
const features=modules.slice(1,7).map(([path,label,description],index)=>({path,label,description,pest:pests[index]}))
const clamp=(value:number,min=0,max=1)=>Math.max(min,Math.min(max,value))
const smooth=(value:number)=>{const t=clamp(value);return t*t*(3-2*t)}
function stemPoint(t:number,p:number){return {x:510+Math.sin(t*5.8+p*1.5-.8)*62+p*t*68,y:24+t*730}}

export function VineWorkspace(){
 const id=useId().replace(/:/g,'')
 const root=useRef<HTMLElement>(null),stem=useRef<SVGPathElement>(null),crest=useRef<SVGPathElement>(null),shade=useRef<SVGPathElement>(null)
 const grains=useRef<(SVGPathElement|null)[]>([]),branches=useRef<(SVGPathElement|null)[]>([]),leaves=useRef<(SVGGElement|null)[]>([]),line=useRef<SVGPathElement>(null),progress=useRef<HTMLSpanElement>(null)
 const panel=useRef<HTMLElement>(null),activeRef=useRef<number|null>(null),paintRef=useRef<()=>void>(()=>{})
 const [active,setActive]=useState<number|null>(null)
 activeRef.current=active
 const feature=active===null?null:features[active]
 function close(restore=false){const previous=activeRef.current;activeRef.current=null;setActive(null);paintRef.current();if(restore&&previous!==null)leaves.current[previous]?.focus({preventScroll:true})}
 function choose(index:number){activeRef.current=index;setActive(index);paintRef.current();requestAnimationFrame(()=>panel.current?.focus({preventScroll:true}))}
 function seek(index:number){
  const el=root.current;if(!el)return
  if(el.dataset.motion==='scroll'){const rect=el.getBoundingClientRect();const top=rect.top+scrollY-88;const range=Math.max(1,el.offsetHeight-innerHeight+88);window.scrollTo({top:top+range*clamp(index*.16+.1),behavior:'smooth'})}
  choose(index)
 }
 useEffect(()=>{
  const el=root.current;if(!el)return
  const reduced=matchMedia('(prefers-reduced-motion: reduce)'),short=matchMedia('(max-height: 560px)')
  let frame=0,last=0,current=0,target=0,visible=false,staticScene=false
  const paint=()=>{
   const p=staticScene ? .92 : current
   el.style.setProperty('--vine-progress',String(p));el.dataset.progress=p.toFixed(3)
   const points=Array.from({length:45},(_,i)=>stemPoint(i/44,p))
   const path=(offset:number,grain=0)=>points.map((point,i)=>(i?'L':'M')+(point.x+offset+Math.sin(i*.7+p)*grain).toFixed(2)+','+point.y.toFixed(2)).join(' ')
   stem.current?.setAttribute('d',path(0));shade.current?.setAttribute('d',path(9));crest.current?.setAttribute('d',path(-8))
   grains.current.forEach((grain,i)=>grain?.setAttribute('d',path((i-2)*5.7,1.7)))
   features.forEach((_,i)=>{
    const t=.145+i*.133,base=stemPoint(t,p),side=i%2===0?1:-1,depth=Math.cos(t*5.8+p*1.5)
    const x=base.x+side*(174+depth*16),y=base.y-15+Math.sin(t*5+p)*10
    const rotation=side*(14+Math.sin(t*5+p)*9)+p*12-8
    const growth=Math.max(smooth((p-(i===0?-.3:i*.14-.04))/.2),activeRef.current===i?1:0)
    const scale=(.93+depth*.08)*(.45+growth*.55),leaf=leaves.current[i]
    leaf?.setAttribute('transform',`translate(${x.toFixed(2)},${y.toFixed(2)}) rotate(${rotation.toFixed(2)}) scale(${scale.toFixed(3)})`)
    leaf?.style.setProperty('opacity',String(growth));leaf?.style.setProperty('pointer-events',growth>.3?'auto':'none');leaf?.setAttribute('tabindex',growth>.3?'0':'-1');leaf?.setAttribute('aria-hidden',String(growth<.05))
    branches.current[i]?.setAttribute('d',`M${base.x},${base.y} C${base.x+side*42},${base.y-4} ${x-side*60},${y+31} ${x-side*20},${y+26}`)
    branches.current[i]?.style.setProperty('opacity',String(growth*.75))
    if(activeRef.current===i)line.current?.setAttribute('d',`M${x+80},${y} C${x+200},${y} 950,358 1080,358`)
   })
   if(progress.current)progress.current.textContent=String(Math.min(6,Math.max(1,Math.floor(p*6)+1))).padStart(2,'0')
  }
  paintRef.current=paint
  const tick=(now:number)=>{frame=0;const dt=Math.min(64,last?now-last:16);last=now;current+=(target-current)*(1-Math.exp(-dt/110));if(Math.abs(current-target)<.0004)current=target;paint();if(visible&&current!==target)frame=requestAnimationFrame(tick)}
  const measure=()=>{if(staticScene)return;const rect=el.getBoundingClientRect(),header=innerWidth<=620?76:88;target=clamp((header-rect.top)/Math.max(1,rect.height-innerHeight+header));if(visible&&!frame){last=0;frame=requestAnimationFrame(tick)}}
  const sync=()=>{cancelAnimationFrame(frame);frame=0;staticScene=reduced.matches||short.matches;el.dataset.motion=reduced.matches?'reduced':short.matches?'static':'scroll';if(!staticScene){measure();current=target}paint()}
  const observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible){measure();paint()}else{cancelAnimationFrame(frame);frame=0}},{rootMargin:'140px'})
  observer.observe(el);addEventListener('scroll',measure,{passive:true});addEventListener('resize',sync);reduced.addEventListener('change',sync);short.addEventListener('change',sync);sync()
  return()=>{cancelAnimationFrame(frame);observer.disconnect();removeEventListener('scroll',measure);removeEventListener('resize',sync);reduced.removeEventListener('change',sync);short.removeEventListener('change',sync);paintRef.current=()=>{}}
 },[])
 useEffect(()=>{if(active===null)return;const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')close(true)};addEventListener('keydown',escape);return()=>removeEventListener('keydown',escape)},[active])
 return <section ref={root} id="workspace" className="vine-workspace" aria-labelledby={id+'title'} onClick={event=>{if(!(event.target as Element).closest('.vine-leaf,.vine-feature-card,.vine-stop'))close()}}>
  <div id="modules" className="vine-stage">
   <div className="vine-atmosphere" aria-hidden="true"/>
   <header className="vine-heading"><p>THE LIVING WORKSPACE</p><h2 id={id+'title'}>循着藤蔓，<br/><span>发现田间。</span></h2><p className="vine-instruction">下滑展开叶片，点击害虫探索功能。</p></header>
   <div className="vine-art"><svg viewBox="0 0 1100 780" className="vine-drawing" aria-label="缠绕的藤蔓与六片害虫叶片"><defs>
    <linearGradient id={id+'bark'} x1="465" y1="0" x2="560" y2="50" gradientUnits="userSpaceOnUse" spreadMethod="reflect"><stop stopColor="#172d1c"/><stop offset=".24" stopColor="#546437"/><stop offset=".5" stopColor="#92a062"/><stop offset=".7" stopColor="#52623b"/><stop offset="1" stopColor="#253b26"/></linearGradient>
    <linearGradient id={id+'leaf'} x1="-100" y1="-100" x2="85" y2="70" gradientUnits="userSpaceOnUse"><stop stopColor="#a5bb6a"/><stop offset=".3" stopColor="#688e4d"/><stop offset=".7" stopColor="#335f3b"/><stop offset="1" stopColor="#183c2b"/></linearGradient>
    <linearGradient id={id+'leafEdge'} x1="-90" y1="-100" x2="90" y2="65" gradientUnits="userSpaceOnUse"><stop stopColor="#c8d78d"/><stop offset="1" stopColor="#51704b" stopOpacity=".3"/></linearGradient>
   </defs><g className="vine-trunk" fill="none" strokeLinecap="round"><path ref={shade} stroke="#000" strokeWidth="44" opacity=".2"/><path ref={stem} stroke={'url(#'+id+'bark)'} strokeWidth="31"/><path ref={crest} stroke="#b2b277" strokeWidth="3" opacity=".35"/>{[0,1,2,3,4].map(i=><path key={i} ref={node=>{grains.current[i]=node}} stroke={i%2?'#172c1c':'#c2c18d'} strokeWidth={i%2?'1.8':'1'} opacity=".26"/>)}{features.map((_,i)=><path key={i} ref={node=>{branches.current[i]=node}} stroke={'url(#'+id+'bark)'} strokeWidth="6"/>)}</g>
   <path ref={line} className={'vine-selection-line'+(active!==null?' visible':'')} fill="none" stroke="#bfcb95" strokeWidth="1" strokeDasharray="3 6"/>
   {features.map((item,i)=><g key={item.path} ref={node=>{leaves.current[i]=node}} className={'vine-leaf'+(active===i?' selected':'')} role="button" tabIndex={i===0?0:-1} aria-hidden={i!==0} aria-label={item.pest+' · 打开'+item.label} aria-expanded={active===i} aria-controls={id+'card'} onClick={event=>{event.stopPropagation();choose(i)}} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose(i)}}}>
    <g className="vine-leaf-surface"><path className="leaf-halo" d="M-112 28C-160-42-85-124 70-113 157-107 144-1 92 46 29 99-62 83-112 28Z"/><path d="M-112 28C-160-42-85-124 70-113 157-107 144-1 92 46 29 99-62 83-112 28Z" fill={'url(#'+id+'leaf)'} stroke={'url(#'+id+'leafEdge)'} strokeWidth="1.5"/>
    <g fill="none" stroke="#d0da94" strokeLinecap="round"><path d="M-112 28Q-25-8 91-91" strokeWidth="1.8" opacity=".65"/><path d="M-66 8-94-53M-26-11-46-94M13-34 15-109M48-61 64-111M-66 8-33 64M-26-11 19 66M13-34 67 49M48-61 110 7" strokeWidth="1" opacity=".24"/></g><g transform={'rotate('+(-13+i*8)+')'}><FieldPest kind={i}/></g><circle cx="-72" cy="19" r="13" fill="#e5eeb6" fillOpacity=".11" stroke="#d9e6a2" strokeOpacity=".55"/><text x="-72" y="23" textAnchor="middle" fill="#e2eabe" fontSize="10" fontFamily="monospace">{i+1}</text></g><text className="vine-pest-name" x="0" y="99" textAnchor="middle">{item.pest}</text>
   </g>)}
   </svg></div>
   {feature&&active!==null?<section key={feature.path} ref={panel} id={id+'card'} className="vine-feature-card" aria-label={feature.label+'功能卡片'} tabIndex={-1}><button className="vine-card-close" aria-label="关闭功能卡片" onClick={()=>close(true)}>×</button><span className="vine-card-eyebrow">叶片 {String(active+1).padStart(2,'0')} / {feature.pest}</span><span className="vine-card-icon"><Icon index={active+1}/></span><h3>{feature.label}</h3><p>{feature.description}</p><Link className="vine-use-feature" to={feature.path}>进入{feature.label}<span aria-hidden="true">↗</span></Link></section>:<aside className="vine-discover-hint"><span className="vine-hint-orbit" aria-hidden="true">↗</span><p>小小叶片，<br/>连接每一次观察。</p><span>点击叶片上的害虫<br/>展开你的功能入口</span></aside>}
   <footer className="vine-scene-footer"><div className="vine-scroll-caption"><span className="vine-scroll-mark" aria-hidden="true"/><span>向下探索</span><span ref={progress}>01</span><span className="vine-divider">/ 06</span></div><nav className="vine-selectors" aria-label="按功能探索叶片">{features.map((item,i)=><button key={item.path} className={'vine-stop'+(active===i?' active':'')} onClick={()=>seek(i)} aria-label={'查看'+item.pest+'与'+item.label} aria-pressed={active===i}><span>0{i+1}</span><span>{item.label}</span></button>)}</nav><span className="vine-field-note">HECHA / FIELD ENCOUNTERS</span></footer>
  </div>
 </section>
}

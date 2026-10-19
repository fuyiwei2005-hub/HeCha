import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { modules } from '../routing'
import { Icon } from './Icon'
import { FieldPest } from './FieldPest'

const pests=['蚜虫','稻飞虱','棉铃虫','白粉虱','蝗虫','蓟马']
const features=modules.slice(1,7).map(([path,label,description],index)=>({path,label,description,pest:pests[index]}))
const clamp=(value:number,min=0,max=1)=>Math.max(min,Math.min(max,value))
const smooth=(value:number)=>{const t=clamp(value);return t*t*(3-2*t)}
function stemPoint(t:number,p:number){return {x:190+t*650+Math.sin(t*8.2+p*1.35)*33,y:10+t*750}}
function normalAt(t:number,p:number){const dx=650+270.6*Math.cos(t*8.2+p*1.35),length=Math.hypot(dx,750);return {x:750/length,y:-dx/length}}

export function VineWorkspace(){
 const id=useId().replace(/:/g,'')
 const root=useRef<HTMLElement>(null),stem=useRef<SVGPathElement>(null),crest=useRef<SVGPathElement>(null),shade=useRef<SVGPathElement>(null)
 const twines=useRef<(SVGPathElement|null)[]>([]),tendrils=useRef<(SVGPathElement|null)[]>([]),buds=useRef<(SVGGElement|null)[]>([]),pending=useRef<number|null>(null)
 const grains=useRef<(SVGPathElement|null)[]>([]),branches=useRef<(SVGPathElement|null)[]>([]),leaves=useRef<(SVGGElement|null)[]>([]),line=useRef<SVGPathElement>(null),progress=useRef<HTMLSpanElement>(null)
 const panel=useRef<HTMLElement>(null),activeRef=useRef<number|null>(null),paintRef=useRef<()=>void>(()=>{})
 const [active,setActive]=useState<number|null>(null)
 activeRef.current=active
 const feature=active===null?null:features[active]
 function close(restore=false){pending.current=null;const previous=activeRef.current;activeRef.current=null;setActive(null);paintRef.current();if(restore&&previous!==null)(root.current?.querySelectorAll<HTMLButtonElement>('.vine-stop')[previous])?.focus({preventScroll:true})}
 function choose(index:number){pending.current=null;activeRef.current=index;setActive(index);paintRef.current();requestAnimationFrame(()=>panel.current?.focus({preventScroll:true}))}
 function seek(index:number){
  const el=root.current;if(!el)return
  if(el.dataset.motion==='scroll'){
   pending.current=index
   const header=innerWidth<=620?76:88,rect=el.getBoundingClientRect(),top=rect.top+scrollY-header,range=Math.max(1,el.offsetHeight-innerHeight+header)
   window.scrollTo({top:top+range*clamp(.25+index*.135),behavior:'smooth'});paintRef.current()
  }else choose(index)
 }
 useEffect(()=>{
  const el=root.current;if(!el)return
  const reduced=matchMedia('(prefers-reduced-motion: reduce)'),short=matchMedia('(max-height: 560px)')
  let frame=0,last=0,current=0,target=0,visible=false,staticScene=false
  const paint=()=>{
   const p=staticScene ? .92 : current
   el.style.setProperty('--vine-progress',String(p));el.dataset.progress=p.toFixed(3)
   const points=Array.from({length:71},(_,i)=>({t:i/70,...stemPoint(i/70,p)}))
   const path=(offset:number,grain=0)=>points.map((point,i)=>{const n=normalAt(point.t,p),shift=offset+Math.sin(i*.67+p)*grain;return (i?'L':'M')+(point.x+n.x*shift).toFixed(2)+','+(point.y+n.y*shift).toFixed(2)}).join(' ')
   stem.current?.setAttribute('d',path(0));shade.current?.setAttribute('d',path(9));crest.current?.setAttribute('d',path(-16))
   grains.current.forEach((grain,i)=>grain?.setAttribute('d',path((i-3)*7.4,1.5)))
   const wrap=(front:boolean,offset=0)=>{let pen=false;return points.map(point=>{const phase=point.t*24+p*1.5,show=(Math.cos(phase)>=0)===front,n=normalAt(point.t,p),shift=Math.sin(phase)*34+offset;const command=(show&&pen?'L':'M')+(point.x+n.x*shift).toFixed(2)+','+(point.y+n.y*shift).toFixed(2);pen=show;return show?command:''}).join(' ')}
   twines.current.forEach((node,i)=>node?.setAttribute('d',wrap(i!==0,i===3?-3:0)))
   if(pending.current!==null){const index=pending.current;if(smooth((p-(.045+index*.135))/.19)>.65){pending.current=null;activeRef.current=index;setActive(index);requestAnimationFrame(()=>panel.current?.focus({preventScroll:true}))}}
   features.forEach((_,i)=>{
    const t=.18+i*.12,base=stemPoint(t,p),side=i%2===0?1:-1,depth=Math.cos(t*7+p*1.3)
    const x=base.x+side*(166+depth*9),y=base.y-side*36
    const rotation=side*(12+Math.sin(t*5+p)*8)+p*10-7
    const growth=smooth((p-(.045+i*.135))/.19)
    if(activeRef.current===i&&growth<.08){activeRef.current=null;setActive(null)}
    const scale=(.92+depth*.06)*(.3+growth*.7),leaf=leaves.current[i]
    leaf?.setAttribute('transform',`translate(${x.toFixed(2)},${y.toFixed(2)}) rotate(${rotation.toFixed(2)}) scale(${scale.toFixed(3)})`)
    leaf?.style.setProperty('opacity',String(growth));leaf?.style.setProperty('pointer-events',growth>.3?'auto':'none');leaf?.setAttribute('tabindex',growth>.3?'0':'-1');leaf?.setAttribute('aria-hidden',String(growth<.05))
    branches.current[i]?.setAttribute('d',`M${base.x},${base.y} C${base.x+side*50},${base.y-2} ${x-side*73},${y+44} ${x-side*35},${y+32}`)
    branches.current[i]?.style.setProperty('opacity',String(growth*.9))
    const curl=Array.from({length:30},(_,j)=>{const f=j/29,angle=f*Math.PI*4.3,radius=27*(1-f)+3;return (j?'L':'M')+(base.x+side*(35+f*18+Math.cos(angle)*radius)).toFixed(2)+','+(base.y+35+Math.sin(angle)*radius).toFixed(2)}).join(' ')
    tendrils.current[i]?.setAttribute('d',`M${base.x},${base.y} Q${base.x+side*20},${base.y+9} ${base.x+side*62},${base.y+35} `+curl.replace(/^M/,'L'))
    tendrils.current[i]?.style.setProperty('opacity',String(.66+growth*.2));buds.current[i]?.setAttribute('transform',`translate(${base.x-side*31},${base.y+31}) rotate(${side*45}) scale(${.78+growth*.17})`);buds.current[i]?.style.setProperty('opacity',String(.82+growth*.12))
    if(activeRef.current===i)line.current?.setAttribute('d',`M${x+80},${y} C${x+200},${y} 950,358 1080,358`)
   })
   if(progress.current)progress.current.textContent=String(Math.min(6,Math.max(0,Math.ceil((p-.045)*6)))).padStart(2,'0')
  }
  paintRef.current=paint
  const tick=(now:number)=>{frame=0;const dt=Math.min(64,last?now-last:16);last=now;current+=(target-current)*(1-Math.exp(-dt/110));if(Math.abs(current-target)<.0004)current=target;paint();if(visible&&current!==target)frame=requestAnimationFrame(tick)}
  const measure=()=>{if(staticScene)return;const rect=el.getBoundingClientRect(),header=innerWidth<=620?76:88;target=clamp((header-rect.top)/Math.max(1,rect.height-innerHeight+header));if(visible&&!frame){last=0;frame=requestAnimationFrame(tick)}}
  const sync=()=>{cancelAnimationFrame(frame);frame=0;staticScene=reduced.matches||short.matches;el.dataset.motion=reduced.matches?'reduced':short.matches?'static':'scroll';pending.current=null;if(!staticScene){measure();current=target}paint()}
  const observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible){measure();paint()}else{cancelAnimationFrame(frame);frame=0}},{rootMargin:'140px'})
  observer.observe(el);addEventListener('scroll',measure,{passive:true});addEventListener('resize',sync);const cancelSeek=()=>{pending.current=null};addEventListener('wheel',cancelSeek,{passive:true});addEventListener('touchstart',cancelSeek,{passive:true});reduced.addEventListener('change',sync);short.addEventListener('change',sync);sync()
  return()=>{cancelAnimationFrame(frame);observer.disconnect();removeEventListener('scroll',measure);removeEventListener('resize',sync);removeEventListener('wheel',cancelSeek);removeEventListener('touchstart',cancelSeek);reduced.removeEventListener('change',sync);short.removeEventListener('change',sync);paintRef.current=()=>{}}
 },[])
 useEffect(()=>{if(active===null)return;const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')close(true)};addEventListener('keydown',escape);return()=>removeEventListener('keydown',escape)},[active])
 return <section ref={root} id="workspace" className="vine-workspace" aria-labelledby={id+'title'} onClick={event=>{if(!(event.target as Element).closest('.vine-leaf,.vine-feature-card,.vine-stop'))close()}}>
  <div id="modules" className="vine-stage">
   <div className="vine-atmosphere" aria-hidden="true"/>
   <header className="vine-heading"><p>THE LIVING WORKSPACE</p><h2 id={id+'title'}>循着藤蔓，<br/><span>发现田间。</span></h2><p className="vine-instruction">下滑展开叶片，点击害虫探索功能。</p></header>
   <div className="vine-art"><svg viewBox="0 0 1100 780" preserveAspectRatio="xMidYMin meet" className="vine-drawing" aria-label="缠绕的藤蔓与六片害虫叶片"><defs>
    <linearGradient id={id+'bark'} x1="0" y1="0" x2="1" y2="0" ><stop stopColor="#343f29"/><stop offset=".22" stopColor="#857f49"/><stop offset=".46" stopColor="#d0b87f"/><stop offset=".65" stopColor="#ad9a63"/><stop offset=".82" stopColor="#6c7442"/><stop offset="1" stopColor="#38492c"/></linearGradient>
    <linearGradient id={id+'leaf'} x1="-100" y1="-100" x2="85" y2="70" gradientUnits="userSpaceOnUse"><stop stopColor="#cbda86"/><stop offset=".2" stopColor="#94b25c"/><stop offset=".47" stopColor="#598948"/><stop offset=".72" stopColor="#315d38"/><stop offset="1" stopColor="#163c28"/></linearGradient>
    <linearGradient id={id+'leafEdge'} x1="-90" y1="-100" x2="90" y2="65" gradientUnits="userSpaceOnUse"><stop stopColor="#c8d78d"/><stop offset="1" stopColor="#51704b" stopOpacity=".3"/></linearGradient>
   </defs><path ref={node=>{twines.current[0]=node}} className="vine-twine-back" fill="none" stroke="#637c38" strokeWidth="15" strokeLinecap="round" opacity=".75"/><g className="vine-trunk" fill="none" strokeLinecap="round"><path ref={shade} stroke="#000" strokeWidth="75" opacity=".25"/><path className="vine-main-stem" ref={stem} stroke={'url(#'+id+'bark)'} strokeWidth="62"/><path ref={crest} stroke="#e5ce94" strokeWidth="8" opacity=".28"/>{[0,1,2,3,4,5,6].map(i=><path key={i} ref={node=>{grains.current[i]=node}} stroke={i%2?'#3b4226':'#e4d2a0'} strokeWidth={i%2?'2.5':'1.2'} opacity=".28"/>)}{features.map((_,i)=><path key={i} ref={node=>{branches.current[i]=node}} stroke={'url(#'+id+'bark)'} strokeWidth="8"/>)}</g><g className="vine-winding-stems" fill="none" strokeLinecap="round"><path ref={node=>{twines.current[1]=node}} stroke="#27351c" strokeWidth="22" opacity=".7"/><path ref={node=>{twines.current[2]=node}} stroke="#9aa35a" strokeWidth="14"/><path ref={node=>{twines.current[3]=node}} stroke="#d0ce86" strokeWidth="2.5" opacity=".55"/>{features.map((_,i)=><path key={i} ref={node=>{tendrils.current[i]=node}} className="vine-tendril" stroke="#a9be56" strokeWidth="1.8"/>)}</g>{features.map((_,i)=><g key={i} ref={node=>{buds.current[i]=node}} className="vine-bud" fill="#91ad4c" stroke="#bccb6a" strokeWidth=".6"><path d="M0 0Q-18-21-30-11Q-22 8 0 0ZM2 1Q14-19 24-14Q21 5 2 1Z"/><path d="M-1 1Q-3 17-13 19Q-19 8-1 1Z" fill="#5d843d"/><path d="M-26-10L0 0L21-12M0 0L-11 16" fill="none" stroke="#d5db93" strokeOpacity=".65"/></g>)}
   <path ref={line} className={'vine-selection-line'+(active!==null?' visible':'')} fill="none" stroke="#bfcb95" strokeWidth="1" strokeDasharray="3 6"/>
   {features.map((item,i)=><g key={item.path} ref={node=>{leaves.current[i]=node}} className={'vine-leaf'+(active===i?' selected':'')} role="button" tabIndex={-1} aria-hidden={true} aria-label={item.pest+' · 打开'+item.label} aria-expanded={active===i} aria-controls={id+'card'} onClick={event=>{event.stopPropagation();choose(i)}} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose(i)}}}>
    <g className="vine-leaf-surface"><g className="vine-leaf-shape" transform={i%2===0?'scale(1 1)':'scale(-1 1)'}><path className="leaf-halo" d="M-126 44C-152-16-103-96-18-102C40-108 86-91 145-126C144-63 124-12 78 27C27 78-70 99-126 44Z"/><path d="M-126 44C-152-16-103-96-18-102C40-108 86-91 145-126C144-63 124-12 78 27C27 78-70 99-126 44Z" fill={'url(#'+id+'leaf)'} stroke={'url(#'+id+'leafEdge)'} strokeWidth="1.5"/>
    <g fill="none" stroke="#d0da94" strokeLinecap="round"><path d="M-126 44Q-28-9 133-111" strokeWidth="1.8" opacity=".65"/><path d="M-80 21Q-106-9-96-57M-39 0Q-62-38-48-91M5-26Q-8-68 24-99M53-64Q54-96 85-105M-80 21Q-52 48-24 66M-39 0Q-5 37 26 52M5-26Q38 5 69 28M53-64Q89-47 119-51" strokeWidth="1" opacity=".24"/></g><path className="vine-leaf-luster" d="M-116 25Q-98-77-20-85Q48-96 121-113Q46-65-3-46Q-70-22-116 25Z" fill="#e5ecaa" opacity=".085"/></g><g transform={'rotate('+(-13+i*8)+')'}><FieldPest kind={i}/></g><circle cx={i%2===0?-72:72} cy="19" r="13" fill="#e5eeb6" fillOpacity=".11" stroke="#d9e6a2" strokeOpacity=".55"/><text x={i%2===0?-72:72} y="23" textAnchor="middle" fill="#e2eabe" fontSize="10" fontFamily="monospace">{i+1}</text></g><text className="vine-pest-name" x="0" y="105" textAnchor="middle">{item.pest}</text>
   </g>)}
   </svg></div>
   {feature&&active!==null?<section key={feature.path} ref={panel} id={id+'card'} className="vine-feature-card" aria-label={feature.label+'功能卡片'} tabIndex={-1}><button className="vine-card-close" aria-label="关闭功能卡片" onClick={()=>close(true)}>×</button><span className="vine-card-eyebrow">叶片 {String(active+1).padStart(2,'0')} / {feature.pest}</span><span className="vine-card-icon"><Icon index={active+1}/></span><h3>{feature.label}</h3><p>{feature.description}</p><Link className="vine-use-feature" to={feature.path}>进入{feature.label}<span aria-hidden="true">↗</span></Link></section>:<aside className="vine-discover-hint"><span className="vine-hint-orbit" aria-hidden="true">↗</span><p>小小叶片，<br/>连接每一次观察。</p><span>点击叶片上的害虫<br/>展开你的功能入口</span></aside>}
   <footer className="vine-scene-footer"><div className="vine-scroll-caption"><span className="vine-scroll-mark" aria-hidden="true"/><span>向下探索</span><span ref={progress}>00</span><span className="vine-divider">/ 06</span></div><nav className="vine-selectors" aria-label="按功能探索叶片">{features.map((item,i)=><button key={item.path} className={'vine-stop'+(active===i?' active':'')} onClick={()=>seek(i)} aria-label={'查看'+item.pest+'与'+item.label} aria-pressed={active===i}><span>0{i+1}</span><span>{item.label}</span></button>)}</nav><span className="vine-field-note">HECHA / FIELD ENCOUNTERS</span></footer>
  </div>
 </section>
}

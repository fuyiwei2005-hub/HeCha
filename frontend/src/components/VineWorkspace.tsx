import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { modules } from '../routing'
import { Icon } from './Icon'
import { FieldPest } from './FieldPest'

const ivyLeaf='M-112 28 Q-91 3-111-25 L-136-62 L-77-60 Q-66-66-65-77 L-72-112 L-16-87 Q-7-83 3-94 L36-139 L64-84 Q70-69 85-68 L145-59 L111-16 Q100-2 114 9 L139 38 L81 50 Q68 53 67 70 L65 91 L14 67 Q-2 60-13 72 L-44 92 L-50 57 Q-53 42-68 44 L-112 51Z'
type Branch={d:string,outline:string,grain:string[],width:number,x:number,y:number}
const treeBranches:Branch[]=[]
function growBranch(x:number,y:number,length:number,angle:number,depth:number,seed:number){
 const endX=x+Math.cos(angle)*length,endY=y+Math.sin(angle)*length
 const bend=.13+Math.sin(seed*1.7)*.16,cx=x+Math.cos(angle+bend)*length*.52,cy=y+Math.sin(angle+bend)*length*.52,width=Math.max(1.1,depth*depth*1.05)
 const points=Array.from({length:23},(_,i)=>{const t=i/22,u=1-t,dx=2*u*(cx-x)+2*t*(endX-cx),dy=2*u*(cy-y)+2*t*(endY-cy),l=Math.hypot(dx,dy);return {x:u*u*x+2*u*t*cx+t*t*endX,y:u*u*y+2*u*t*cy+t*t*endY,nx:-dy/l,ny:dx/l,r:width*.62*(1-t*.61)*(1+Math.sin(t*18+seed)*.045)}})
 const edge=(side:number)=>points.map(p=>`${(p.x+p.nx*p.r*side).toFixed(2)},${(p.y+p.ny*p.r*side).toFixed(2)}`)
 const outline='M'+edge(1).join('L')+'L'+edge(-1).reverse().join('L')+'Z'
 const grain=[-.55,-.12,.35].map((offset,k)=>points.map((p,i)=>(i?'L':'M')+(p.x+p.nx*p.r*(offset+Math.sin(i*.45+seed+k)*.07)).toFixed(2)+','+(p.y+p.ny*p.r*(offset+Math.sin(i*.45+seed+k)*.07)).toFixed(2)).join(' '))
 treeBranches.push({d:`M${x} ${y}Q${cx} ${cy} ${endX} ${endY}`,outline,grain,width,x:endX,y:endY})
 if(depth>0){growBranch(endX,endY,length*(.66+Math.sin(seed)*.045),angle-.42-Math.sin(seed*2)*.10,depth-1,seed+1);growBranch(endX,endY,length*(.72+Math.cos(seed)*.035),angle+.49+Math.cos(seed*1.3)*.12,depth-1,seed+3)}
}

growBranch(1140,100,295,-3.02,4,2)
growBranch(1130,250,225,-2.99,4,9)
growBranch(1080,-55,290,-3.05,4,4)
const treeFoliage=treeBranches.filter(b=>b.width<5).flatMap((b,i)=>Array.from({length:7},(_,j)=>({x:b.x+Math.sin(i*2.3+j*3)*37,y:b.y+Math.cos(i*1.7+j*2)*32,rotation:Math.sin(i*3+j)*125,size:.11+(i%4)*.014,start:.23+(i%17)*.009})))
const mix=(a:number[],b:number[],t:number)=>`rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*clamp(t))).join(',')})`
const pests=['蚜虫','稻飞虱','棉铃虫','白粉虱','蝗虫','蓟马']
const features=modules.slice(1,7).map(([path,label,description],index)=>({path,label,description,pest:pests[index]}))
const clamp=(value:number,min=0,max=1)=>Math.max(min,Math.min(max,value))
const smooth=(value:number)=>{const t=clamp(value);return t*t*(3-2*t)}
const restingLeaves=[{x:185,y:570,angle:-24},{x:455,y:690,angle:19},{x:805,y:515,angle:-14},{x:375,y:460,angle:32},{x:665,y:735,angle:-29},{x:945,y:680,angle:15}]

export function VineWorkspace(){
 const id=useId().replace(/:/g,'')
 const root=useRef<HTMLElement>(null),foliage=useRef<(SVGGElement|null)[]>([]),season=useRef<HTMLSpanElement>(null),pending=useRef<number|null>(null)
 const leaves=useRef<(SVGGElement|null)[]>([]),progress=useRef<HTMLSpanElement>(null)
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
   const header=innerWidth<=800?76:88,rect=el.getBoundingClientRect(),top=rect.top+scrollY-header,range=Math.max(1,el.offsetHeight-innerHeight+header)
   window.scrollTo({top:top+range*clamp(.91+index*.014),behavior:'smooth'});paintRef.current()
  }else choose(index)
 }
 useEffect(()=>{
  const el=root.current;if(!el)return
  const reduced=matchMedia('(prefers-reduced-motion: reduce)'),short=matchMedia('(max-height: 560px)')
  let frame=0,last=0,current=0,target=0,visible=false,staticScene=false
  const paint=()=>{
   const p=staticScene ? 1 : current
   el.style.setProperty('--vine-progress',String(p));el.dataset.progress=p.toFixed(3)
   const autumn=smooth((p-.57)/.23)
   el.style.setProperty('--season-warmth',String(autumn))
   if(season.current)season.current.textContent=p<.19?'冬 · 静候新生':p<.47?'春 · 枝叶初生':p<.66?'夏 · 绿意繁盛':p<.82?'秋 · 层林染金':'秋 · 落叶知时'
   foliage.current.forEach((node,i)=>{const item=treeFoliage[i],growth=smooth((p-item.start)/.15);node?.setAttribute('transform',`translate(${item.x},${item.y}) rotate(${item.rotation}) scale(${item.size*growth})`);node?.style.setProperty('opacity',String(growth));node?.style.setProperty('color',mix([76+i%4*12,132+i%3*10,52],[206+i%3*12,137+i%4*9,36],autumn))})
   if(pending.current!==null&&p>.87){const index=pending.current;pending.current=null;activeRef.current=index;setActive(index);requestAnimationFrame(()=>panel.current?.focus({preventScroll:true}))}
   features.forEach((_,i)=>{
    const growth=smooth((p-(.80+i*.008))/.06),fall=smooth((p-(.82+i*.008))/.14),from=treeBranches[treeBranches.length-1-i*7],rest=restingLeaves[i]
    const drift=Math.sin(fall*Math.PI*(2.2+i*.13)+i)*Math.sin(fall*Math.PI)
    const x=from.x+(rest.x-from.x)*fall+drift*(55+i*7),y=from.y+(rest.y-from.y)*fall+Math.sin(fall*Math.PI*2+i)*Math.sin(fall*Math.PI)*20
    const rotation=rest.angle*fall+Math.sin(fall*Math.PI*3+i)*Math.sin(fall*Math.PI)*45,leaf=leaves.current[i]
    leaf?.setAttribute('transform',`translate(${x.toFixed(2)},${y.toFixed(2)}) rotate(${rotation.toFixed(2)}) scale(${(.57+i%3*.025)*(.3+growth*.7)})`)
    leaf?.style.setProperty('opacity',String(growth));leaf?.style.setProperty('pointer-events',growth>.65?'auto':'none');leaf?.setAttribute('tabindex',growth>.65?'0':'-1');leaf?.setAttribute('aria-hidden',String(growth<.05))
    if(activeRef.current===i&&growth<.08){activeRef.current=null;setActive(null)}
   })
   if(progress.current)progress.current.textContent=String(Math.min(6,Math.max(0,Math.ceil((p-.80)/.018)))).padStart(2,'0')
  }
  paintRef.current=paint
  const tick=(now:number)=>{frame=0;const dt=Math.min(64,last?now-last:16);last=now;current+=(target-current)*(1-Math.exp(-dt/110));if(Math.abs(current-target)<.0004)current=target;paint();if(visible&&current!==target)frame=requestAnimationFrame(tick)}
  const measure=()=>{if(staticScene)return;const rect=el.getBoundingClientRect(),header=innerWidth<=800?76:88;target=clamp((header-rect.top)/Math.max(1,rect.height-innerHeight+header));if(visible&&!frame){last=0;frame=requestAnimationFrame(tick)}}
  const sync=()=>{cancelAnimationFrame(frame);frame=0;staticScene=reduced.matches||short.matches;el.dataset.motion=reduced.matches?'reduced':short.matches?'static':'scroll';pending.current=null;if(!staticScene){measure();current=target}paint()}
  const observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible){measure();paint()}else{cancelAnimationFrame(frame);frame=0}},{rootMargin:'140px'})
  observer.observe(el);addEventListener('scroll',measure,{passive:true});addEventListener('resize',sync);const cancelSeek=()=>{pending.current=null};addEventListener('wheel',cancelSeek,{passive:true});addEventListener('touchstart',cancelSeek,{passive:true});reduced.addEventListener('change',sync);short.addEventListener('change',sync);sync()
  return()=>{cancelAnimationFrame(frame);observer.disconnect();removeEventListener('scroll',measure);removeEventListener('resize',sync);removeEventListener('wheel',cancelSeek);removeEventListener('touchstart',cancelSeek);reduced.removeEventListener('change',sync);short.removeEventListener('change',sync);paintRef.current=()=>{}}
 },[])
 useEffect(()=>{if(active===null)return;const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')close(true)};addEventListener('keydown',escape);return()=>removeEventListener('keydown',escape)},[active])
 return <section ref={root} id="workspace" className="vine-workspace" aria-labelledby={id+'title'} onClick={event=>{if(!(event.target as Element).closest('.vine-leaf,.vine-feature-card,.vine-stop'))close()}}>
  <div id="modules" className="vine-stage">
   <div className="vine-atmosphere" aria-hidden="true"/>
   <svg className="season-illustration" viewBox="0 0 1100 900" preserveAspectRatio="xMidYMax slice" aria-hidden="true"><defs><linearGradient id={id+'sky'} x2="0" y2="1"><stop stopColor="#c8e8ec"/><stop offset=".65" stopColor="#f1f4d9"/><stop offset="1" stopColor="#fff0c5"/></linearGradient><linearGradient id={id+'hill'} x2="0" y2="1"><stop stopColor="#91bba4"/><stop offset="1" stopColor="#b6cfa5"/></linearGradient></defs><path fill={'url(#'+id+'sky)'} d="M0 0H1100V900H0Z"/><circle className="anime-sun-halo" cx="245" cy="260" r="112" fill="#fff4bd" opacity=".38"/><circle cx="245" cy="260" r="65" fill="#fff8d8"/><g className="anime-cloud cloud-one" fill="#fffff5" stroke="#e5efe5" strokeWidth="2"><path d="M70 353C37 353 38 319 66 313C65 281 106 268 125 291C145 257 202 271 206 304C244 293 268 317 252 341Q239 354 213 353Z"/><path d="M96 342Q146 352 205 339" fill="none" stroke="#dce9df"/></g><g className="anime-cloud cloud-two" fill="#fffdf0"><path d="M471 208C443 205 448 176 473 173C479 144 518 144 531 165C551 142 587 154 590 179C619 176 634 194 617 207Z"/></g><g className="anime-cloud cloud-three" fill="#fffff5" opacity=".8"><path d="M48 507C19 506 20 481 45 475C54 447 87 452 97 470C118 452 153 469 153 487Q187 492 171 507Z"/></g><path d="M0 700Q140 599 271 665T550 653T832 646T1100 630V900H0Z" fill="#b7d0bf"/><path d="M0 744Q161 651 323 717T643 701T1100 681V900H0Z" fill={'url(#'+id+'hill)'}/><path d="M0 798Q190 731 365 779T737 771T1100 746V900H0Z" fill="#cad7a3"/><path d="M0 854Q240 763 511 829T1100 799V900H0Z" fill="#e6dfa9"/><g fill="none" stroke="#faf2c7" strokeWidth="3" opacity=".65"><path d="M20 890Q225 788 463 829M220 900Q425 808 628 850M620 900Q837 797 1080 834"/></g><g fill="#6d9881" opacity=".7"><path d="M61 744l9-37 10 37ZM80 739l12-48 13 48ZM964 705l10-38 12 38ZM984 710l13-51 14 51Z"/></g><g className="anime-sparkles" fill="#fffef2"><path d="M132 412l3 8 8 3-8 3-3 8-3-8-8-3 8-3ZM359 525l3 7 7 3-7 3-3 7-3-7-7-3 7-3ZM889 564l3 9 9 3-9 3-3 9-3-9-9-3 9-3Z"/></g></svg>

   <header className="vine-heading"><p>A YEAR IN ONE TREE</p><h2 id={id+'title'}>一树四季，<br/><span>落叶知时。</span></h2><p className="vine-instruction">随下滑见证生长，点击秋日落叶探索功能。</p></header>
   <div className="vine-art"><svg viewBox="0 0 1100 780" preserveAspectRatio="xMidYMid meet" className="vine-drawing" aria-label="随滚动从冬到秋生长的树木与六片功能落叶"><defs>
    <linearGradient id={id+'bark'}><stop stopColor="#65513e"/><stop offset=".32" stopColor="#a58b68"/><stop offset=".6" stopColor="#8f7355"/><stop offset="1" stopColor="#5c4837"/></linearGradient>
    <linearGradient id={id+'leaf'} x1="0" y1="0" x2="1" y2="1"><stop stopColor="#ecd485"/><stop offset=".45" stopColor="#cfaa49"/><stop offset="1" stopColor="#8a5d2c"/></linearGradient>
    <linearGradient id={id+'leafEdge'}><stop stopColor="#f5d78a"/><stop offset="1" stopColor="#a67c38"/></linearGradient>
   </defs><g className="tree-distant-landscape" aria-hidden="true"><path d="M0 620L85 580L160 604L260 555L350 586L440 560L540 601L680 566L780 606L920 570L1100 610V780H0Z" fill="#a7ad8b" opacity=".2"/><path d="M0 687L120 648L240 682L380 621L530 667L650 631L790 675L930 642L1100 684V780H0Z" fill="#899777" opacity=".16"/></g>
   <g className="season-tree-branches" strokeLinecap="round" strokeLinejoin="round">{treeBranches.map((branch,i)=><g key={i}><path d={branch.outline} fill={'url(#'+id+'bark)'} stroke="#65503d" strokeWidth=".45"/>{branch.width>3&&branch.grain.map((d,k)=><path key={k} d={d} fill="none" stroke={k===0?'#dec29a':'#533e30'} strokeWidth={k===0?'.85':'.55'} opacity={k===0?'.4':'.22'}/>)}</g>)}</g>
   <g className="season-tree-foliage" pointerEvents="none" aria-hidden="true">{treeFoliage.map((_,i)=><g key={i} ref={node=>{foliage.current[i]=node}} opacity="0"><path d={ivyLeaf} fill="currentColor"/><path d="M-106 35L23-29L35-125M23-29L-62-102M23-29L132-56M23-29L62 79M23-29L-40 81" fill="none" stroke="#f1e3b2" strokeOpacity=".28" strokeWidth="3"/></g>)}</g>
   {features.map((item,i)=><g key={item.path} ref={node=>{leaves.current[i]=node}} className={'vine-leaf'+(active===i?' selected':'')} role="button" tabIndex={-1} aria-hidden={true} aria-label={item.pest+' · 打开'+item.label} aria-expanded={active===i} aria-controls={id+'card'} onClick={event=>{event.stopPropagation();choose(i)}} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose(i)}}}>
    <g className="vine-leaf-surface"><g className="vine-leaf-shape" transform={i%2===0?'scale(1 1)':'scale(-1 1)'}><path className="leaf-halo" d={ivyLeaf}/><path d={ivyLeaf} fill={'url(#'+id+'leaf)'} stroke={'url(#'+id+'leafEdge)'} strokeWidth="1.5"/>
    <g fill="none" stroke="#d0da94" strokeLinecap="round"><path d="M-108 38Q-30 23 26-29L37-126" strokeWidth="1.8" opacity=".65"/><path d="M26-29Q-27-46-63-101M26-29Q80-52 130-57M26-29Q61 13 63 78M-11 2Q-30 49-40 80M-11 2Q-73-18-124-56M54-43L53-76M77-52L96-38M43 0L88 17M-24-44L-54-68" strokeWidth="1" opacity=".24"/></g><path className="vine-leaf-luster" d="M-104 26L-119-51L-76-50L-62-92L-17-71L34-119L46-78Q19-19-104 26Z" fill="#e5ecaa" opacity=".085"/></g><g transform={'rotate('+(-13+i*8)+')'}><FieldPest kind={i}/></g><circle cx={i%2===0?-72:72} cy="19" r="13" fill="#e5eeb6" fillOpacity=".11" stroke="#d9e6a2" strokeOpacity=".55"/><text x={i%2===0?-72:72} y="23" textAnchor="middle" fill="#e2eabe" fontSize="10" fontFamily="monospace">{i+1}</text></g><text className="vine-pest-name" x="0" y="105" textAnchor="middle">{item.pest}</text>
   </g>)}
   </svg></div>
   {feature&&active!==null?<section key={feature.path} ref={panel} id={id+'card'} className="vine-feature-card" aria-label={feature.label+'功能卡片'} tabIndex={-1}><button className="vine-card-close" aria-label="关闭功能卡片" onClick={()=>close(true)}>×</button><span className="vine-card-eyebrow">叶片 {String(active+1).padStart(2,'0')} / {feature.pest}</span><span className="vine-card-icon"><Icon index={active+1}/></span><h3>{feature.label}</h3><p>{feature.description}</p><Link className="vine-use-feature" to={feature.path}>进入{feature.label}<span aria-hidden="true">↗</span></Link></section>:<aside className="vine-discover-hint"><span className="vine-hint-orbit" aria-hidden="true">↗</span><p>从静候新生，<br/>到一叶知秋。</p><span ref={season} className="tree-season-label">冬 · 静候新生</span><span>秋日落叶，连接六种田间能力。</span></aside>}
   <footer className="vine-scene-footer"><div className="vine-scroll-caption"><span className="vine-scroll-mark" aria-hidden="true"/><span>向下探索</span><span ref={progress}>00</span><span className="vine-divider">/ 06</span></div><nav className="vine-selectors" aria-label="按功能探索叶片">{features.map((item,i)=><button key={item.path} className={'vine-stop'+(active===i?' active':'')} onClick={()=>seek(i)} aria-label={'查看'+item.pest+'与'+item.label} aria-pressed={active===i}><span>0{i+1}</span><span>{item.label}</span></button>)}</nav><span className="vine-field-note">HECHA / FIELD ENCOUNTERS</span></footer>
  </div>
 </section>
}

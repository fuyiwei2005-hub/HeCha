import { useEffect, useRef } from 'react'
import { FieldVisual } from './FieldVisual'
const chapters = [
 ['01 / OBSERVE','从一片叶子，','走近田间细节。','照片与视频，记录每一次观察。'],
 ['02 / RECOGNIZE','让目标，','逐渐清晰。','定位虫体，呈现类别与检测线索。'],
 ['03 / UNDERSTAND','从看见，','走向理解。','结合参考资料，复核防治建议。'],
]
export function ScrollStory(){
 const root=useRef<HTMLElement>(null)
 useEffect(()=>{
  const el=root.current;if(!el)return
  const media=matchMedia('(prefers-reduced-motion: reduce)')
  let frame=0,current=0,target=0,visible=false,last=0
  const texts=Array.from(el.querySelectorAll<HTMLElement>('.story-chapter'))
  const paint=()=>{
   el.style.setProperty('--story-progress',String(current))
   const stage=Math.round(current*2)
   texts.forEach((text,i)=>{text.setAttribute('aria-hidden',String(i!==stage));text.inert=i!==stage;const distance=(current*2-i);text.style.opacity=String(Math.max(0,1-Math.abs(distance)*1.6));text.style.transform=`translate3d(0,${Math.max(-32,Math.min(32,distance*-35))}px)`})
   el.querySelectorAll('.story-marker').forEach((dot,i)=>dot.classList.toggle('active',i===stage))
  }
  const tick=(now:number)=>{frame=0;const dt=Math.min(64,last?now-last:16);last=now;current+=(target-current)*(1-Math.exp(-dt/95));if(Math.abs(target-current)<.0005)current=target;paint();if(visible&&current!==target)frame=requestAnimationFrame(tick)}
  const measure=()=>{if(media.matches)return;const rect=el.getBoundingClientRect();target=Math.max(0,Math.min(1,-rect.top/Math.max(1,rect.height-innerHeight)));if(visible&&!frame){last=0;frame=requestAnimationFrame(tick)}}
  const sync=()=>{el.classList.toggle('story-reduced',media.matches);if(media.matches){cancelAnimationFrame(frame);frame=0;texts.forEach(text=>{text.removeAttribute('aria-hidden');text.inert=false;text.style.opacity='';text.style.transform=''})}else{measure();current=target;paint()}}
  const observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible)measure();else{cancelAnimationFrame(frame);frame=0}},{rootMargin:'120px'})
  observer.observe(el);addEventListener('scroll',measure,{passive:true});addEventListener('resize',measure);media.addEventListener('change',sync);sync()
  return()=>{cancelAnimationFrame(frame);observer.disconnect();removeEventListener('scroll',measure);removeEventListener('resize',measure);media.removeEventListener('change',sync)}
 },[])
 return <section ref={root} className="scroll-story" aria-label="滚动探索识别流程"><div className="story-sticky"><div className="story-art"><FieldVisual technical/><div className="story-scan"/><div className="story-focus"/></div><div className="story-copy">{chapters.map(([label,title,subtitle,description],i)=><div key={label} className="story-chapter" aria-hidden={i!==0}><p className="brand-eyebrow">{label}</p><h2>{title}<br/><span>{subtitle}</span></h2><p>{description}</p></div>)}</div><div className="story-bottom"><span>随滚动，深入观察</span><div className="story-track"><i/></div><div className="story-markers">{chapters.map(([label],i)=><span key={label} className={'story-marker'+(i===0?' active':'')}>0{i+1}</span>)}</div></div></div></section>
}

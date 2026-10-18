import { useEffect } from 'react'
/** Native scrolling, compositor-only motion and no render loop while the page rests. */
export function usePageMotion(pathname:string){
 useEffect(()=>{
  const media=matchMedia('(prefers-reduced-motion: reduce)')
  const animations=new Set<Animation>(),seen=new WeakSet<Element>()
  let observer:IntersectionObserver|undefined,mutations:MutationObserver|undefined
  const selector='.route-heading,.capture-main,.capture-guide,.result-section-head,.information-intro,.info-tile,.module-card,.metric,.model-details-heading,.promise-steps>div,.brand-closing,.brand-promise>h2'
  const setup=()=>{
   observer?.disconnect();mutations?.disconnect();animations.forEach(a=>a.cancel());animations.clear()
   if(media.matches)return
   observer=new IntersectionObserver(entries=>{
    let index=0
    entries.forEach(entry=>{if(!entry.isIntersecting)return;observer?.unobserve(entry.target);const a=entry.target.animate([{opacity:0,transform:'translate3d(0,24px,0)'},{opacity:1,transform:'translate3d(0,0,0)'}],{duration:760,delay:Math.min(index++*65,260),easing:'cubic-bezier(.16,1,.3,1)',fill:'backwards'});animations.add(a);a.onfinish=()=>animations.delete(a)})
   },{threshold:.06,rootMargin:'0px 0px -24px 0px'})
   const discover=()=>document.querySelectorAll(selector).forEach(el=>{if(!seen.has(el)){seen.add(el);observer?.observe(el)}})
   discover();mutations=new MutationObserver(discover);const main=document.querySelector('main');if(main)mutations.observe(main,{childList:true,subtree:true})
  }
  setup();media.addEventListener('change',setup)
  return()=>{observer?.disconnect();mutations?.disconnect();animations.forEach(a=>a.cancel());media.removeEventListener('change',setup)}
 },[pathname])
}

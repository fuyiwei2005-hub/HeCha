import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listDetections, Detection } from '../api'
export function TaskNotifications({onError}:{onError:(e:unknown)=>void}) {
  const previous=useRef(new Map<string,string>()),ready=useRef(false)
  const [notices,setNotices]=useState<Detection[]>([])
  const query=useQuery({queryKey:['detections','list','video'],queryFn:({signal})=>listDetections(signal,'video'),refetchInterval:q=>q.state.data?.some(d=>['queued','processing'].includes(d.status))?3000:15000})
  useEffect(()=>{if(query.error)onError(query.error)},[query.error,onError])
  useEffect(()=>{
    if(!query.data)return
    const finished=query.data.filter(d=>ready.current&&['queued','processing'].includes(previous.current.get(d.id)||'')&&['completed','failed'].includes(d.status))
    previous.current=new Map(query.data.map(d=>[d.id,d.status]));ready.current=true
    if(finished.length)setNotices(old=>[...finished,...old.filter(d=>!finished.some(n=>n.id===d.id))].slice(0,5))
  },[query.data])
  return <div className="task-notices" aria-live="polite">{notices.map(d=><div className="task-notice" key={d.id}><Link to={'/history?record='+encodeURIComponent(d.id)} onClick={()=>setNotices(a=>a.filter(n=>n.id!==d.id))}>{d.status==='completed'?'视频识别已完成':'视频处理失败，可重试'}：{d.original_name} ↗</Link><button className="icon-btn" aria-label="关闭任务提醒" onClick={()=>setNotices(a=>a.filter(n=>n.id!==d.id))}>×</button></div>)}</div>
}

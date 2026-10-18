import { useState } from 'react'
import { Prediction } from '../api'

export function VideoTimeline({ events, onSeek }: {
  events: { time_ms: number; detections: Prediction[] }[]
  onSeek: (seconds: number) => void
}) {
  const [open, setOpen] = useState(false)
  const [limit, setLimit] = useState(50)
  if (!events.length) return null
  return <div className="video-timeline">
    <button className="btn btn-sm btn-ghost" onClick={() => setOpen(!open)} aria-expanded={open}>
      {open ? '收起检出时间点' : `查看 ${events.length} 个检出时间点`}
    </button>
    {open && <div className="timeline-list">
      {events.slice(0, limit).map((event, index) => {
        const names = [...new Set(event.detections.map((p) => p.class_cn || p.class))].join('、')
        const seconds = event.time_ms / 1000
        return <button key={index} className="timeline-event" onClick={() => onSeek(seconds)}>
          <span>{Math.floor(seconds / 60)}:{(seconds % 60).toFixed(1).padStart(4, '0')}</span>
          <span>{names} · {event.detections.length} 次检出</span>
        </button>
      })}
      {events.length > limit && <button className="btn btn-sm btn-ghost" onClick={() => setLimit(limit + 50)}>显示更多时间点</button>}
    </div>}
  </div>
}

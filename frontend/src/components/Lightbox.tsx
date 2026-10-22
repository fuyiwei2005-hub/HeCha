import { useEffect, useState } from 'react'

export function Lightbox({
  url, caption, onClose,
}: { url: string; caption: string; onClose: () => void }) {
  const [zoom,setZoom]=useState(1)
  // Esc 关闭 + 打开期间锁滚动：这两个是放大查看的基本预期，
  // 少了任何一个用户都会觉得"卡住了"
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [onClose])

  return (
    <div className="lightbox" onClick={onClose} role="dialog" aria-modal="true" aria-label="查看大图">
      <div className="lightbox-bar">
        <a
          className="btn btn-sm"
          href={url}
          download
          onClick={(e) => e.stopPropagation()}
        >
          下载当前图片
        </a>
        <label onClick={e=>e.stopPropagation()}>放大 {Math.round(zoom*100)}% <input aria-label="图片缩放" type="range" min="1" max="4" step="0.25" value={zoom} onChange={e=>setZoom(Number(e.target.value))}/></label>
        <button className="btn btn-sm" onClick={onClose}>关闭 ✕</button>
      </div>
      <div className="lightbox-viewport" onClick={e=>e.stopPropagation()}><img src={url} alt={caption} style={{width:`${zoom*100}%`,maxWidth:'none',maxHeight:'none'}}/></div>
      <div className="lightbox-caption">{caption}</div>
    </div>
  )
}

import { useEffect } from 'react'

export function Lightbox({
  url, caption, onClose,
}: { url: string; caption: string; onClose: () => void }) {
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
          下载原图
        </a>
        <button className="btn btn-sm" onClick={onClose}>关闭 ✕</button>
      </div>
      <img src={url} alt={caption} onClick={(e) => e.stopPropagation()} />
      <div className="lightbox-caption">{caption}</div>
    </div>
  )
}

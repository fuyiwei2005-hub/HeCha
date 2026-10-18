import { useCallback, useRef, useState } from 'react'

export type ToastKind = 'success' | 'error' | 'info'
export type ToastItem = { id: number; kind: ToastKind; text: string }

/** 简易 toast 中心：错误/成功统一走它，避免每个页面各写一套提示条 */
export function useToasts() {
  const [items, setItems] = useState<ToastItem[]>([])
  const seq = useRef(0)

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (kind: ToastKind, text: string, ttl = 4200) => {
      const id = ++seq.current
      setItems((prev) => [...prev.slice(-3), { id, kind, text }])
      window.setTimeout(() => dismiss(id), ttl)
      return id
    },
    [dismiss],
  )

  const success = useCallback((t: string) => push('success', t), [push])
  const error = useCallback((t: string) => push('error', t, 6000), [push])
  const info = useCallback((t: string) => push('info', t), [push])

  return { items, push, dismiss, success, error, info }
}

export function Toaster({
  items,
  onDismiss,
}: {
  items: ToastItem[]
  onDismiss: (id: number) => void
}) {
  return (
    <div className="toaster" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`}>
          <span>{t.text}</span>
          <button className="toast-close" onClick={() => onDismiss(t.id)} aria-label="关闭提示">
            ×
          </button>
        </div>
      ))}
    </div>
  )
}

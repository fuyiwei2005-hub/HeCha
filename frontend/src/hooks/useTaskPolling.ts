import { useEffect, useState } from 'react'

/** Schedule the next poll only after the current request settles. */
export function useTaskPolling(activeKey: string, load: () => Promise<void>) {
  const [hint, setHint] = useState<string | null>(null)
  useEffect(() => {
    setHint(null)
    if (!activeKey) return
    let cancelled = false
    let timer: number | undefined
    let rounds = 0
    async function poll() {
      if (cancelled) return
      if (document.visibilityState !== 'hidden' && navigator.onLine) {
        await load()
        rounds += 1
      }
      if (cancelled) return
      if (rounds >= 300) {
        setHint('处理时间较长，自动刷新已暂停。可点击刷新查看最新结果。')
        return
      }
      timer = window.setTimeout(poll, 3000)
    }
    timer = window.setTimeout(poll, 1500)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [activeKey, load])
  return hint
}

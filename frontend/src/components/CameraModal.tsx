import { useEffect, useRef, useState } from 'react'

export function CameraModal({
  onCapture, onClose,
}: { onCapture: (file: File) => void; onClose: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [error, setError] = useState('')
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function start() {
      // 非安全上下文（http 部署）下浏览器直接禁用 getUserMedia：
      // 不提前判断的话，点击拍照只会得到一个含糊的 NotAllowedError。
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('当前环境不支持摄像头。请通过 HTTPS 访问，或改用「选择图片」上传。')
        return
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment' }, audio: false,
        })
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play().catch(() => undefined)
        }
        setReady(true)
      } catch (err) {
        setError(`无法打开摄像头：${(err as Error).name === 'NotAllowedError' ? '权限被拒绝' : (err as Error).message}`)
      }
    }
    start()

    // 关闭时务必停掉所有轨道，否则摄像头指示灯一直亮着，用户会以为被偷拍
    return () => {
      cancelled = true
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }, [])

  useEffect(() => {
    const close = (event: KeyboardEvent) => {if (event.key === 'Escape') onClose()}
    document.addEventListener('keydown', close)
    return () => document.removeEventListener('keydown', close)
  }, [onClose])

  function capture() {
    const video = videoRef.current
    if (!video || !video.videoWidth) return
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d')?.drawImage(video, 0, 0)
    canvas.toBlob((blob) => {
      if (!blob) { setError('截图失败，请重试'); return }
      const file = new File([blob], `camera_${Date.now()}.jpg`, { type: 'image/jpeg' })
      onCapture(file)
    }, 'image/jpeg', 0.92)
  }

  return (
    <div className="dialog-mask" onClick={onClose} role="dialog" aria-modal="true" aria-label="拍照识别">
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h3>拍照识别</h3>
          <button className="icon-btn" onClick={onClose} aria-label="关闭">✕</button>
        </div>
        <div className="dialog-body">
          <div className="cam-view">
            <video ref={videoRef} playsInline muted />
            {!ready && !error && <div className="cam-note"><span className="spinner" />正在启动摄像头…</div>}
            {error && <div className="cam-note">{error}</div>}
          </div>
        </div>
        <div className="dialog-foot">
          <button className="btn btn-ghost" onClick={onClose}>取消</button>
          <button className="btn btn-lime" onClick={capture} disabled={!ready}>
            拍照并识别
          </button>
        </div>
      </div>
    </div>
  )
}

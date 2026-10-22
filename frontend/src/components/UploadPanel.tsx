import { Icon } from './Icon'
import { DragEvent, useRef, useState } from 'react'
import { CropOption } from '../api'

type Props = {
  mode?: 'image' | 'video'
  crops: CropOption[]
  crop: string
  onCrop: (v: string) => void
  busy: boolean
  busyLabel: string | null
  onPickImage: (file: File) => void
  onPickVideo: (file: File) => void
  onCamera: () => void
  cameraBlocked: boolean
}

const IMAGE_EXT = ['image/jpeg', 'image/png', 'image/webp']
const VIDEO_EXT = ['video/mp4', 'video/webm', 'video/quicktime']

/* 与后端 config.py 的 max_image_bytes / max_video_bytes 保持一致。
   在客户端先拦一道：否则用户选中一个 800MB 的视频后会立刻进入 busy 态，
   必须等整段上行跑完（或超时）才拿到 413，全程没有进度也无法取消。 */
const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const MAX_VIDEO_BYTES = 100 * 1024 * 1024

const mb = (n: number) => (n / 1048576).toFixed(1)

export function UploadPanel({
  mode = 'image', crops, crop, onCrop, busy, busyLabel,
  onPickImage, onPickVideo, onCamera, cameraBlocked,
}: Props) {
  const [over, setOver] = useState(false)
  const imageInput = useRef<HTMLInputElement>(null)
  const videoInput = useRef<HTMLInputElement>(null)

  // 拖拽落下的可能是任意文件，按 MIME 分流到对应链路，
  // 类型不认识时给明确提示，而不是静默无反应（评委拖拽失败会以为是坏了）。
  function route(file: File) {
    if (busy) return
    // 相机/微信来源的 file.type 可能是空串，这时按扩展名兜底判断，
    // 否则会误报"不支持的文件类型"
    const type = file.type
    const name = file.name.toLowerCase()
    const isImage = IMAGE_EXT.includes(type) || /\.(jpe?g|png|webp)$/.test(name)
    const isVideo = VIDEO_EXT.includes(type) || /\.(mp4|webm|mov)$/.test(name)

    if (file.size === 0) { alert('文件为空，请重新选择'); return }
    if ((mode === 'image' && !isImage) || (mode === 'video' && !isVideo)) {alert(mode === 'image' ? '请上传图片' : '请上传视频'); return}
    if (isImage) {
      if (file.size > MAX_IMAGE_BYTES) {
        alert(`图片过大：${mb(file.size)}MB，上限 ${mb(MAX_IMAGE_BYTES)}MB\n请压缩后再上传。`)
        return
      }
      onPickImage(file)
    } else if (isVideo) {
      if (file.size > MAX_VIDEO_BYTES) {
        alert(`视频过大：${mb(file.size)}MB，上限 ${mb(MAX_VIDEO_BYTES)}MB\n请压缩或裁剪后再上传。`)
        return
      }
      onPickVideo(file)
    } else {
      alert(`不支持的文件类型：${file.type || '未知'}\n请上传 JPG/PNG/WEBP 图片或 MP4/WEBM/MOV 视频`)
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setOver(false)
    if (busy) return
    const file = e.dataTransfer.files?.[0]
    if (file) route(file)
  }

  return (
    <div className="upload-panel">
      <div
        className={`dropzone${over ? ' is-over' : ''}${busy ? ' dropzone-busy' : ''}`}
        onDragOver={(e) => { e.preventDefault(); if (!busy) setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        onClick={() => !busy && (mode === 'image' ? imageInput : videoInput).current?.click()}
        role="button"
        aria-disabled={busy}
        aria-busy={busy}
        tabIndex={busy ? -1 : 0}
        aria-label={mode === 'image' ? '拖拽或点击上传图片' : '拖拽或点击上传视频'}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (!busy) (mode === 'image' ? imageInput : videoInput).current?.click() }
        }}
      >
        {busy ? (
          <>
            <span className="spinner" />
            <b>{busyLabel ?? '处理中…'}</b>
            <small>图片检测通常需要数秒，视频会更久</small>
          </>
        ) : (
          <>
            <span className="dropzone-icon" aria-hidden="true"><Icon index={mode === 'image' ? 1 : 2}/></span>
            <b>{mode === 'image' ? '拖入照片，或点击选择' : '拖入视频，或点击选择'}</b>
            <small>{mode === 'image' ? '支持 JPG / PNG / WEBP，单张 ≤ 10 MB' : '支持 MP4 / WEBM / MOV，单个 ≤ 100 MB'}</small>
          </>
        )}
      </div>

      <div className="upload-controls">
      {<div className="upload-row">
        <label className="crop-field" style={{ flex: '1 1 180px' }}>
          <span>这是什么作物（可选）</span>
          <select
            className="select"
            value={crop}
            onChange={(e) => onCrop(e.target.value)}
            disabled={crops.length === 0}
          >
            <option value="">不指定</option>
            {crops.map((c) => (
              <option key={c.key} value={c.key}>{c.label}</option>
            ))}
          </select>
        </label>
      </div>

      }
      <div className="upload-buttons">
        {mode === 'image' && <button className="btn btn-lime" onClick={() => imageInput.current?.click()} disabled={busy}>
          选择图片
        </button>}
        {mode === 'video' && <button className="btn" onClick={() => videoInput.current?.click()} disabled={busy}>
          上传视频
        </button>}
        {mode === 'image' && !cameraBlocked && (
          <button className="btn" onClick={onCamera} disabled={busy}>
            拍照识别
          </button>
        )}
      </div>

      </div>
      {mode === 'image' && cameraBlocked && (
        <p className="limit-note">
          当前浏览器无法使用摄像头，请使用「选择图片」上传。
        </p>
      )}
      <p className="limit-note">{mode === 'image' ? '单张图片 ≤10 MB · ≤2500 万像素；选择文件后自动开始识别。' : '单个视频 ≤100 MB；选择文件后自动上传并创建任务。'}</p>

      <input
        id="imgFile" aria-label="选择图片文件" ref={imageInput} hidden type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) { route(f); e.target.value = '' } }}
      />
      <input
        id="vidFile" aria-label="选择视频文件" ref={videoInput} hidden type="file"
        accept="video/mp4,video/webm,video/quicktime"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) { route(f); e.target.value = '' } }}
      />
    </div>
  )
}

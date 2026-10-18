import { useState } from 'react'
import { Detection, retryVideo } from '../api'
export function VideoProgress({item,onUpdated,onError}: {item: Detection;onUpdated:(item:Detection)=>void;onError:(error:unknown)=>void}) {
  const [busy,setBusy] = useState(false)
  if (item.media_type !== 'video' || item.status === 'completed') return null
  const progress = item.progress
  const labels: Record<string,string> = {queued:'等待处理',starting:'正在准备视频',detecting:'正在逐帧识别',converting:'识别完成，正在转码',failed:'任务未完成'}
  async function retry() {if (busy) return;setBusy(true);try {onUpdated(await retryVideo(item.id))} catch(error){onError(error)} finally{setBusy(false)}}
  return <div className="video-progress" role="status"><b>{labels[progress?.stage || item.status] || '正在处理视频'}</b>
    {progress && progress.total_frames>0 && <><p>已处理 {progress.processed_frames} / {progress.total_frames} 帧{progress.percent !== null ? ' · '+progress.percent+'%' : ''}</p><progress aria-label="视频帧处理进度" max={100} value={progress.percent ?? undefined}/></>}
    {item.status==='queued' && <p>{item.error || '任务已保存，可以离开页面，稍后返回查看。'}</p>}
    {item.status==='failed' && <><p>{item.error || '视频处理失败'}</p>{progress?.can_retry && <button className="btn btn-sm" disabled={busy} onClick={retry}>{busy?'正在提交…':'重试视频'}</button>}</>}
  </div>
}

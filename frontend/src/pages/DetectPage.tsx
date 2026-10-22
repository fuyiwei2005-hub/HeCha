import { ObservationFields } from '../components/ObservationFields'
import { emptyObservation } from '../api'
import { Icon } from '../components/Icon'
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useOutletContext } from 'react-router-dom'
import { listCrops, uploadImage, uploadVideo } from '../api'
import { PageContext } from '../components/AppLayout'
import { CameraModal } from '../components/CameraModal'
import { DetectionCard } from '../components/DetectionCard'
import { UploadPanel } from '../components/UploadPanel'
import { useRecords } from '../hooks/useRecords'
export function DetectPage({media}: {media: 'image' | 'video'}) {
  const context = useOutletContext<PageContext>(), records = useRecords(context.onError,media)
  const crops = useQuery({queryKey: ['crops'], queryFn: listCrops, staleTime: 300000})
  const [crop, setCrop] = useState(() => localStorage.getItem('pg_crop') || '')
  const [busy, setBusy] = useState(false), [camera, setCamera] = useState(false), [latest, setLatest] = useState<string | null>(null)
  const [observation,setObservation]=useState({...emptyObservation}),[progress,setProgress]=useState(0),[failedFile,setFailedFile]=useState<File|null>(null)
  const lock = useRef(false)
  useEffect(() => {if (crops.error) context.onError(crops.error)}, [crops.error, context.onError])
  async function submit(file: File) {
    if (lock.current) return
    lock.current = true; setBusy(true);setProgress(0);setFailedFile(null)
    try {
      const result = media === 'image' ? await uploadImage(file, crop || undefined,observation,setProgress) : await uploadVideo(file,crop||undefined,observation,setProgress)
      records.update(result); setLatest(result.id)
      context.notify(media === 'image' ? '识别结果已保存，防治建议将自动更新' : '视频已提交，处理结果将自动更新')
    } catch (error) {setFailedFile(file);context.onError(error)} finally {lock.current = false; setBusy(false)}
  }
  const visible = records.items.filter(item => media === 'video' ? item.media_type === 'video' : item.id === latest)
  return <section id={media === 'image' ? 'console' : 'videoUpload'}>
    <p className="muted">{media === 'image' ? '上传照片或拍照，查看标注结果与防治建议。' : '上传田间视频，后台处理期间可以离开本页，稍后返回查看。'}</p>
    <div className="capture-workspace"><div className="capture-main"><div className="capture-heading"><span className="step-label">01 / 上传素材</span><span className="capture-format">{media === 'image' ? '图片 · 相机' : '视频 · 后台处理'}</span></div>
    <details className="capture-context"><summary>补充田间信息（选填）</summary><p className="muted">先填写地块与观察情况，再选择素材开始识别。</p><ObservationFields value={observation} onChange={setObservation} disabled={busy}/></details>
    {busy&&<div className="upload-progress" role="status"><progress max={100} value={progress}/><span>{progress<100?`正在上传 ${progress}%`:'上传完成，服务器正在处理…'}</span></div>}
    {failedFile&&!busy&&<div className="alert alert-warn">上传未能确认，请先<Link to="/history">查看历史记录</Link>。<button className="btn btn-sm" onClick={()=>submit(failedFile)}>重试上传</button></div>}
    <UploadPanel mode={media} crops={crops.data?.crops || []} crop={crop} onCrop={value => {setCrop(value); localStorage.setItem('pg_crop',value)}} busy={busy} busyLabel={media === 'image' ? '正在识别图片…' : '正在上传视频…'} onPickImage={submit} onPickVideo={submit} onCamera={() => setCamera(true)} cameraBlocked={!window.isSecureContext || !navigator.mediaDevices?.getUserMedia}/></div>
    <aside className="capture-guide"><span className="guide-icon"><Icon index={media === 'image' ? 1 : 2}/></span><h2>{media === 'image' ? '拍得清楚，识别更有依据。' : '一段视频，留住田间细节。'}</h2><p>{media === 'image' ? '靠近目标，保持画面清晰。选择作物后，再上传图片。' : '保持镜头稳定，让目标在画面中清晰可见。'}</p><ul><li><span>01</span>{media === 'image' ? '对焦虫体，尽量保留叶片环境' : '选择需要分析的田间视频'}</li><li><span>02</span>{media === 'image' ? '使用自然光，减少模糊与遮挡' : '提交后可离开，任务在后台处理'}</li><li><span>03</span>{media === 'image' ? '查看标注，再结合参考资料复核' : '返回查看结果与检出时间点'}</li></ul><Link to="/history">查看历史记录 <span aria-hidden="true">↗</span></Link></aside></div>
    <div className="result-section-head"><div><span className="step-label">02 / 查看分析</span><h2 className="results-heading">{media === 'video' ? '视频任务与结果' : '本次识别结果'}</h2></div><span className="result-hint">{busy ? '正在处理素材…' : visible.length ? '结果与建议自动保存' : '等待上传'}</span></div>
    {records.error && <p className="alert alert-error">结果加载失败。<button className="btn btn-sm" onClick={() => void records.refetch()}>重新加载</button></p>}
    <div className="grid">{visible.map(item => <DetectionCard key={item.id} item={item} onDeleted={records.remove} onUpdated={records.update} onError={context.onError} onZoom={context.onZoom}/>)}</div>
    {!visible.length && <div className="result-placeholder" role="status"><span className="placeholder-icon"><Icon index={busy ? 5 : 7}/></span><div><h3>{busy ? '正在准备你的识别结果' : media === 'video' ? '暂无视频任务' : '下一次观察，从这里开始'}</h3><p>{busy ? '请稍候，完成后将在这里显示。' : media === 'video' ? '上传视频后，可在这里查看进度、播放结果与检出时间线。' : '上传图片后，结果会显示在这里；以前的结果可在历史记录查看。'}</p></div></div>}
    {camera && <CameraModal onClose={() => setCamera(false)} onCapture={file => {setCamera(false); void submit(file)}}/>}
  </section>
}

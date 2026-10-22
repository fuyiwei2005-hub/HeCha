import { FormEvent, useEffect, useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { deleteAllDetections } from '../api'
import { PageContext } from '../components/AppLayout'
import { DetectionCard } from '../components/DetectionCard'
import { recordsKey } from '../hooks/useRecords'
import { useRecordPage } from '../hooks/useRecordPage'
const PAGE_SIZE = 20
function dateBoundary(value: string | null, nextDay = false) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined
  const date = new Date(value+'T00:00:00')
  if (!Number.isFinite(date.getTime())) return undefined
  if (nextDay) date.setDate(date.getDate()+1)
  return date.toISOString()
}
export function RecordsPage() {
  const context = useOutletContext<PageContext>(), client = useQueryClient()
  const [params,setParams] = useSearchParams()
  const raw = params.toString(), parsedPage = Number(params.get('page') || 1)
  const page = Number.isSafeInteger(parsedPage) && parsedPage > 0 && parsedPage < 1000000 ? parsedPage : 1
  const media = ['image','video'].includes(params.get('type') || '') ? params.get('type')! : ''
  const status = ['queued','processing','completed','failed'].includes(params.get('status') || '') ? params.get('status')! : ''
  const [keyword,setKeyword] = useState(params.get('q') || ''), [start,setStart] = useState(params.get('start') || ''), [end,setEnd] = useState(params.get('end') || '')
  const [field,setField]=useState(params.get('field')||'')
  const [draftStatus,setDraftStatus] = useState(status), [clearing,setClearing] = useState(false)
  useEffect(() => {setField(params.get('field')||'');setKeyword(params.get('q') || '');setStart(params.get('start') || '');setEnd(params.get('end') || '');setDraftStatus(status)}, [raw])
  const records = useRecordPage({detection_id:params.get('record')||undefined,field_name:params.get('field')||undefined,offset:(page-1)*PAGE_SIZE,limit:PAGE_SIZE,media_type:media,status,q:params.get('q')?.slice(0,100),start_at:dateBoundary(params.get('start')),end_at:dateBoundary(params.get('end'),true)},context.onError)
  const pages = Math.max(1,Math.ceil(records.total/PAGE_SIZE))
  function change(values: Record<string,string>, reset = true) {
    const next = new URLSearchParams(params)
    for (const [key,value] of Object.entries(values)) {if (value) next.set(key,value);else next.delete(key)}
    if (reset) next.delete('page')
    setParams(next)
  }
  useEffect(() => {if (records.data && !records.isFetching && page > pages) change({page:String(pages)},false)}, [records.data,records.isFetching,page,pages])
  function apply(event: FormEvent) {
    event.preventDefault()
    if (start && end && start > end) {context.onError(new Error('开始日期不能晚于结束日期'));return}
    change({q:keyword.trim(),field:field.trim(),start,end,status:draftStatus})
  }
  async function clear() {
    if (!confirm('确定清空全部检测记录及结果文件？此操作包括当前筛选之外的记录。')) return
    setClearing(true)
    try {await client.cancelQueries({queryKey:recordsKey});await deleteAllDetections();await client.invalidateQueries({queryKey:recordsKey});await client.invalidateQueries({queryKey:['statistics']});setParams({});context.notify('记录已清空')}
    catch (error) {context.onError(error)} finally {setClearing(false)}
  }
  return <section id="history" className="section">
    <div className="section-head"><p>识别结果、参考资料与追问记录</p><div className="filters">
      <button className="btn btn-sm" onClick={() => void records.refetch()}>刷新</button>
      <button className="btn btn-sm btn-ghost" disabled={clearing || !records.total} onClick={clear}>清空记录</button>
      {['','image','video'].map(value => <button className="chip" key={value} aria-pressed={media===value} onClick={() => change({type:value})}>{!value?'全部':value==='image'?'图片':'视频'}</button>)}
    </div></div>
    <form className="record-search" onSubmit={apply}>
      <label>地块名称<input className="input" value={field} maxLength={80} onChange={e=>setField(e.target.value)} placeholder="按地块查看连续观察"/></label>
      <label>关键词<input className="input" value={keyword} maxLength={100} onChange={e=>setKeyword(e.target.value)} placeholder="文件名、作物或虫种"/></label>
      <label>开始日期<input className="input" type="date" value={start} onChange={e=>setStart(e.target.value)}/></label>
      <label>结束日期<input className="input" type="date" min={start||undefined} value={end} onChange={e=>setEnd(e.target.value)}/></label>
      <label>任务状态<select className="select" value={draftStatus} onChange={e=>setDraftStatus(e.target.value)}><option value="">全部状态</option><option value="queued">排队中</option><option value="processing">处理中</option><option value="completed">已完成</option><option value="failed">失败</option></select></label>
      <button className="btn" type="submit">筛选</button><button className="btn btn-ghost" type="button" onClick={()=>setParams({})}>重置筛选</button>
    </form>
    {records.isPending && <p role="status">正在加载记录…</p>}
    {records.error && <p className="alert alert-error">记录加载失败，请点击刷新重试。</p>}
    {!records.isPending && !records.error && <p className="record-count" aria-live="polite">共 {records.total} 条记录 · 第 {page} / {pages} 页</p>}
    <div className="grid">{records.items.map(item=><DetectionCard key={item.id} item={item} onDeleted={records.remove} onUpdated={records.update} onError={context.onError} onZoom={context.onZoom}/>)}</div>
    {!records.isPending && !records.error && !records.items.length && <div className="empty">暂无符合条件的检测记录</div>}
    {!records.isPending && !records.error && records.total>0 && <nav className="record-pagination" aria-label="记录分页"><button className="btn btn-sm" disabled={page<=1||records.isFetching} onClick={()=>change({page:String(page-1)},false)}>上一页</button><span>第 {page} / {pages} 页</span><button className="btn btn-sm" disabled={page>=pages||records.isFetching} onClick={()=>change({page:String(page+1)},false)}>下一页</button></nav>}
  </section>
}

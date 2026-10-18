import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import { fetchStatistics } from '../api'
import { PageContext } from '../components/AppLayout'
export function StatisticsPage() {
  const context = useOutletContext<PageContext>()
  const query = useQuery({queryKey: ['statistics'], queryFn: fetchStatistics})
  useEffect(() => {if (query.error) context.onError(query.error)}, [query.error, context.onError])
  const data = query.data
  return <section id="statistics"><button className="btn btn-sm" onClick={() => void query.refetch()}>刷新统计</button>
    {query.isPending && <p role="status">正在加载统计…</p>}
    {query.error && <p className="alert alert-error">统计加载失败，请刷新重试。</p>}
    {data && <><div id="stats" className="module-grid">{[['累计检测',data.total_jobs],['图片记录',data.image_jobs],['视频记录',data.video_jobs],['已完成',data.completed_jobs],['失败任务',data.failed_jobs],['检出次数',data.total_objects]].map(([label,value]) => <div className="card metric" key={label}><strong>{value}</strong><p>{label}</p></div>)}</div>
      <h2>虫种分布</h2><p className="muted">视频中的跨帧检出次数不等于独立虫体数量。</p><div className="distribution">{(data.classes || []).map(item => <div className="distribution-row" key={item.name}><span>{item.name_cn || item.name}</span><meter min={0} max={Math.max(...data.classes.map(row => row.count),1)} value={item.count}/><b>{item.count}</b></div>)}{!data.classes?.length && <p className="empty">暂无虫种统计</p>}</div></>}
  </section>
}

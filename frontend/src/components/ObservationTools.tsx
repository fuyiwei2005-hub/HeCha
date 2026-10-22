import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Comparison, comparePests, Detection, emptyObservation, saveObservation, refreshAdvice } from '../api'
import { ObservationFields } from './ObservationFields'
import { makeReport, downloadReport } from '../report'
export function ObservationTools({item,onUpdated,onError}:{item:Detection;onUpdated:(d:Detection)=>void;onError:(e:unknown)=>void}) {
  const [draft,setDraft]=useState({...emptyObservation,...item.observation}),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[report,setReport]=useState<File|null>(null)
  const [comparisons,setComparisons]=useState<Comparison[]|null>(null),[comparing,setComparing]=useState(false)
  async function compare(){setComparing(true);try{setComparisons(await comparePests(item.id))}catch(e){onError(e)}finally{setComparing(false)}}
  async function save(regenerate=false){setBusy(true);setMessage('');try{const saved=await saveObservation(item.id,draft);onUpdated(saved);if(regenerate)onUpdated(await refreshAdvice(item.id));setMessage(regenerate?'已保存，建议将根据新信息重新生成':'田间档案与纠错已保存')}catch(e){onError(e)}finally{setBusy(false)}}
  async function exportReport(){setBusy(true);try{const file=await makeReport(item);setReport(file);downloadReport(file);setMessage('报告已下载，可用浏览器打开并打印为 PDF')}catch(e){onError(e)}finally{setBusy(false)}}
  async function share(){if(!report)return;try{await navigator.share({files:[report],title:'禾察田间观察报告'})}catch(e){if(!(e instanceof DOMException&&e.name==='AbortError'))onError(e)}}
  return <div className="observation-tools">
    {item.quality&&<div className="quality-notes"><strong>拍摄与复核提示</strong>{item.quality.warnings.length?<ul>{item.quality.warnings.map(w=><li key={w}>{w}</li>)}</ul>:<p>未发现明显画质问题，仍需结合现场情况复核。</p>}<small>{item.quality.method}</small></div>}
    {item.observation?.field_name&&<Link className="field-archive-link" to={'/history?field='+encodeURIComponent(item.observation.field_name)}>查看「{item.observation.field_name}」连续观察记录 ↗</Link>}
    {item.observation?.notes&&<p className="field-note">{item.observation.notes}</p>}
    {item.observation?.correction&&<p>用户纠错（待复核）：{item.observation.correction}</p>}
    <details onToggle={e=>{if(e.currentTarget.open)setDraft({...emptyObservation,...item.observation})}}><summary>田间档案 / 识别不准确</summary><ObservationFields value={draft} onChange={setDraft} disabled={busy}/><label>纠错说明（待复核）<textarea aria-label="纠错说明（待复核）" className="input" maxLength={500} rows={2} value={draft.correction} onChange={e=>setDraft({...draft,correction:e.target.value})} placeholder="疑似其他虫种、漏检位置或误检原因"/></label><p className="muted">纠错保留为用户反馈，不会直接修改模型识别结论。更新田间信息后可主动重新生成建议。</p><div className="observation-actions"><button className="btn btn-sm" disabled={busy} onClick={()=>save()}>保存田间档案</button><button className="btn btn-sm btn-ghost" disabled={busy||item.status!=='completed'||['queued','processing'].includes(item.analysis_status)} onClick={()=>save(true)}>保存并更新建议</button></div></details>
    {item.status==='completed'&&<details><summary onClick={()=>{if(comparisons===null&&!comparing)void compare()}}>相近虫种 / 症状对照</summary><p className="muted">按知识库同科、同目条目对照典型受害症状；对照项不是本次检出结果，也不代表外观相同。资料为教学整理，需结合现场复核。</p>{comparing?<p role="status">正在查阅资料…</p>:comparisons?.length?comparisons.map(c=><div className="comparison-reference" key={c.id}><strong>{c.title} · {c.detected?'本次候选':'对照条目'}</strong><p>{c.symptoms}</p><small>{c.source}</small></div>):<p>暂无匹配对照资料，可补拍局部近照后咨询农技人员。</p>}</details>}
    <div className="observation-actions"><button className="btn btn-sm btn-ghost" disabled={busy} onClick={exportReport}>导出观察报告</button>{report&&navigator.canShare?.({files:[report]})&&<button className="btn btn-sm" onClick={share}>分享已导出报告</button>}</div><p role="status">{message}</p>
  </div>
}

import { Detection, Prediction, getResultUrl } from './api'
const escape=(s:unknown)=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!))
export async function makeReport(item:Detection):Promise<File> {
  let picture=''
  if(item.media_type==='image'&&item.result_url){
    const url=await getResultUrl(item.id)
    if(!url)throw new Error('标注图暂不可用，请重试后导出完整报告')
    const response=await fetch(url,{signal:AbortSignal.timeout(30000)})
    if(!response.ok)throw new Error('报告图片加载失败，请重试')
    const blob=await response.blob()
    picture=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(new Error('图片读取失败'));reader.readAsDataURL(blob)})
    if(!/^data:image\/(png|jpeg|webp);base64,/.test(picture))throw new Error('报告图片格式不受支持')
  }
  const predictions:Prediction[]=item.media_type==='image'?item.predictions as Prediction[]:(item.predictions as {detections:Prediction[]}[]).flatMap(e=>e.detections||[])
  const names=[...new Set(predictions.map(p=>p.class_cn||p.class))]
  const o=item.observation
  const html=`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>禾察田间观察报告</title><style>body{max-width:800px;margin:40px auto;padding:24px;font:16px/1.8 system-ui;color:#243c32}h1{font-size:28px}h2{font-size:19px;border-bottom:1px solid #ddd}img{max-width:100%;max-height:400px;object-fit:contain}p,li{overflow-wrap:anywhere;white-space:pre-wrap}small{color:#63736a}@media print{body{margin:0;padding:0;font-size:11pt}img{max-height:250px}h2{break-after:avoid}li{break-inside:avoid}}@page{margin:18mm}</style><h1>禾察 · 田间观察报告</h1><small>当前记录快照 · 可通过浏览器菜单打印或另存为 PDF</small><p>观察时间：${escape(new Date(item.created_at).toLocaleString('zh-CN'))}\n文件：${escape(item.original_name)}\n地块：${escape(o?.field_name||'未填写')} · 作物：${escape(item.crop||'未填写')}\n生长阶段：${escape(o?.growth_stage||'未填写')} · 自述程度：${escape(o?.severity||'未填写')}</p>${picture?`<img alt="识别标注图" src="${picture}">`:''}<h2>识别结果</h2><p>${escape(names.join('、')||'暂无检出结果')}\n识别状态：${escape(item.status)} · 建议状态：${escape(item.analysis_status)}\n${item.media_type==='video'?'视频跨帧检出不等于独立虫体数量。':''}</p><p>${escape(item.quality?.warnings.join('\n'))}</p><h2>田间笔记</h2><p>${escape(o?.notes||'暂无')}</p>${o?.correction?`<p>用户纠错（待复核）：${escape(o.correction)}</p>`:''}<h2>分析与行动建议</h2><p>${escape(item.analysis||'当前暂无建议，分析完成后可重新导出。')}</p><h2>参考资料</h2><ol>${(item.references||[]).map(r=>`<li>[${escape(r.ref)}] ${escape(r.title||r.id)}<br>${escape(r.body)}<br><small>${escape(r.source)}</small></li>`).join('')}</ol><small>模型结果供辅助观察，画质提示不判定识别正确性。报告包含你填写的田间信息。</small></html>`
  return new File([html],`禾察观察报告-${item.id.slice(0,8)}.html`,{type:'text/html;charset=utf-8'})
}
export function downloadReport(file:File){const url=URL.createObjectURL(file),a=document.createElement('a');a.href=url;a.download=file.name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000)}

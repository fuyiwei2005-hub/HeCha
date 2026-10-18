import { useState } from 'react'
import { Detection, retryAnalysis } from '../api'

export function AnalysisStatus({ item, onUpdated, onError }: {
  item: Detection; onUpdated: (item: Detection) => void; onError: (error: unknown) => void
}) {
  const [busy, setBusy] = useState(false)
  if (item.status !== 'completed' || item.analysis_status === 'completed' || item.analysis_status === 'skipped') return null
  const pending = item.analysis_status === 'queued' || item.analysis_status === 'processing'
  async function retry() {
    setBusy(true)
    try { onUpdated(await retryAnalysis(item.id)) } catch (error) { onError(error) }
    finally { setBusy(false) }
  }
  return <div className="advice" role="status" style={{ padding: '1rem' }}>
    <b>AI 防治建议</b>
    <p>{pending ? '识别结果已就绪，防治建议正在生成…'
      : item.analysis_status === 'disabled' ? '识别已完成，当前未启用 AI 建议。'
      : item.analysis_error || '建议暂时无法生成，识别结果仍可查看。'}</p>
    {pending && <span className="spinner" aria-label="正在生成建议" />}
    {['failed', 'disabled'].includes(item.analysis_status) && <button className="btn btn-sm" onClick={retry} disabled={busy}>
      {busy ? '正在提交…' : '重试建议'}
    </button>}
  </div>
}

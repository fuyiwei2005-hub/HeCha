import { ObservationTools } from './ObservationTools'
import { originalImage } from '../api'
import { VideoProgress } from './VideoProgress'
import { AnalysisStatus } from './AnalysisStatus'
import { VideoTimeline } from './VideoTimeline'
import { ReactNode, useEffect, useRef, useState } from 'react'
import {
  ChatMessage, Detection, Prediction, Reference,
  deleteDetection, forgetResultUrl, getChatHistory, getResultUrl, sendChat, submitFeedback,
} from '../api'

/* ── 从两种 predictions 结构中摊平成目标列表 ── */
function extractPredictions(item: Detection): Prediction[] {
  if (item.media_type === 'image') return (item.predictions as Prediction[]) || []
  const events = (item.predictions as { time_ms: number; detections: Prediction[] }[]) || []
  return events.flatMap((ev) => ev.detections || [])
}

type PestGroup = { name: string; nameEn: string; count: number; maxConf: number }
function groupByPest(preds: Prediction[]): PestGroup[] {
  const map = new Map<string, PestGroup>()
  for (const p of preds) {
    const name = p.class_cn || p.class
    const hit = map.get(name)
    if (hit) {
      hit.count += 1
      hit.maxConf = Math.max(hit.maxConf, p.raw_confidence ?? p.confidence)
    } else {
      map.set(name, { name, nameEn: p.class, count: 1, maxConf: p.raw_confidence ?? p.confidence })
    }
  }
  return [...map.values()].sort((a, b) => b.count - a.count || b.maxConf - a.maxConf)
}

const STATUS_TEXT: Record<string, string> = {
  completed: '已完成', processing: '处理中', queued: '排队中', failed: '失败',
}

/** 把正文里的 [1][2] 渲染成可点击角标。
 *  用 React 元素而非 innerHTML —— 后端返回的字符串由 React 自动转义，
 *  不会像 v-html / dangerouslySetInnerHTML 那样形成 XSS 入口。 */
function renderWithRefs(text: string, onJump: (n: number) => void): ReactNode {
  return text.split(/(\[\d+\])/g).map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/)
    if (m) {
      const n = Number(m[1])
      return (
        <button
          key={i}
          className="ref"
          onClick={(e) => { e.stopPropagation(); onJump(n) }}
          aria-label={`查看参考文献 ${n}`}
        >
          {n}
        </button>
      )
    }
    return <span key={i}>{part}</span>
  })
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

/* ── 主组件 ── */
export function DetectionCard({
  item, onDeleted, onUpdated, onError, onZoom,}: {
  item: Detection
  onDeleted: (id: string) => void
  onUpdated: (item: Detection) => void
  /**
   * 上报错误时**必须把原始错误对象**交给父组件，不要在这里降级成字符串。
   * 父组件要靠 `err instanceof SessionExpiredError` 判断会话是否失效；
   * 一旦这里先 `.message` 掉，会话过期就只会变成一句 toast，
   * 用户会卡在"已登录但所有操作都失败"的界面（登录页不会出现）。
   */
  onError: (err: unknown) => void
  onZoom: (url: string, caption: string) => void
}) {
  const preds = extractPredictions(item)
  const groups = groupByPest(preds)
  const totalObjects = preds.length
  const videoRef = useRef<HTMLVideoElement>(null)

  const [vote, setVote] = useState<'good' | 'bad' | null>(item.feedback || null)
  const [adviceOpen, setAdviceOpen] = useState(true)
  const [refsOpen, setRefsOpen] = useState(false)

  /* 追问 */
  const [chatOpen, setChatOpen] = useState(false)
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const loaded = useRef(false)

  useEffect(() => {
    if (chatOpen && !loaded.current) {
      loaded.current = true
      getChatHistory(item.id).then(setHistory).catch((err) => { loaded.current = false; onError(err) })
    }
  }, [chatOpen, item.id])

  const [original,setOriginal]=useState<string|null>(null),[showOriginal,setShowOriginal]=useState(false),[loadingOriginal,setLoadingOriginal]=useState(false)
  useEffect(()=>()=>{if(original)URL.revokeObjectURL(original)},[original])
  async function compare(){
    if(loadingOriginal)return
    if(showOriginal){setShowOriginal(false);return}
    if(original){setShowOriginal(true);return}
    setLoadingOriginal(true)
    try{const blob=await originalImage(item.id);setOriginal(URL.createObjectURL(blob));setShowOriginal(true)}catch(e){onError(e)}finally{setLoadingOriginal(false)}
  }
  const isImage = item.media_type === 'image'
  const hasRefs = !!item.references?.length

  /* 结果文件需要先换一张短时票据（见 api.ts 注释）。
     票据是异步获取的，所以放在 state 里，拿到之前先显示占位。 */
  const [mediaUrl, setMediaUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!item.result_url) { setMediaUrl(null); return }
    let cancelled = false
    getResultUrl(item.id).then((url) => { if (!cancelled) setMediaUrl(url) })
      .catch((err) => { if (!cancelled) onError(err) })
    return () => { cancelled = true }
  }, [item.id, item.result_url])

  const displayUrl=showOriginal?original:mediaUrl

  async function vote_(rating: 'good' | 'bad') {
    if (vote) return
    try {
      await submitFeedback(item.id, rating)
      setVote(rating)
      onUpdated({...item, feedback: rating})
    } catch (err) {
      onError(err)
    }
  }

  async function remove() {
    // 删记录是不可逆操作，必须有确认；但也不该像"清空全部"那样苛刻——
    // 删一条自己的记录是常规操作，普通确认足够。
    if (!window.confirm(`删除这条记录？\n\n${item.original_name}\n\n相关图片也会一并移除。`)) return
    try {
      await deleteDetection(item.id)
      forgetResultUrl(item.id)
      onDeleted(item.id)
    } catch (err) {
      onError(err)
    }
  }

  async function send() {
    const text = draft.trim()
    if (!text || chatBusy) return
    setDraft('')
    setChatBusy(true)
    setHistory((h) => [...h, { role: 'user', content: text, created_at: new Date().toISOString() }])
    try {
      const resp = await sendChat(item.id, text)
      setHistory((h) => [
        ...h,
        { role: 'assistant', content: resp.reply, created_at: new Date().toISOString() },
      ])
    } catch (err) {
      onError(err)
      setHistory((h) => h.slice(0, -1))
    } finally {
      setChatBusy(false)
    }
  }

  function jumpToRef(n: number) {
    setRefsOpen(true)
    requestAnimationFrame(() => {
      document.getElementById(`ref-${item.id}-${n}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }

  return (
    <article id={`record-${item.id}`} className="card detection rise">
      {/* ── 媒体 ── */}
      <div className="detection-media">
        {displayUrl && isImage ? (
          <>
            <img
              src={displayUrl}
              alt={`${item.original_name} 的${showOriginal?'原图':'识别标注图'}`}
              loading="lazy"
              onClick={() => onZoom(displayUrl, item.original_name)}
            />
            <span className="media-zoom">点击放大</span>
          </>
        ) : mediaUrl && !isImage ? (
          <video
            ref={videoRef}
            src={mediaUrl}
            controls
            preload="metadata"
            style={{ width: '100%', height: '100%', objectFit: 'cover', background: '#000' }}
          />
        ) : (
          <div className={`media-fallback ${item.status === 'processing' || item.status === 'queued' ? 'processing' : item.status === 'failed' ? 'failed' : 'done'}`}>
            {item.status === 'processing' || item.status === 'queued' ? (
              <>
                <span className="spinner" />
                <span>视频正在逐帧分析…</span>
                <small style={{ opacity: 0.7, fontWeight: 400 }}>完成后会自动刷新</small>
              </>
            ) : item.status === 'failed' ? (
              <span>{item.error || '处理失败'}</span>
            ) : (
              <span>暂无结果图</span>
            )}
          </div>
        )}
      </div>

      <div className="detection-body">
        {/* ── 标题行 ── */}
        {isImage&&mediaUrl&&<button className="btn btn-sm" disabled={loadingOriginal} onClick={compare}>{loadingOriginal?'正在加载原图…':showOriginal?'查看标注图':'查看原图对比'}</button>}
        {mediaUrl && <a className="btn btn-sm btn-ghost" href={mediaUrl} download>下载标注结果</a>}
        <div className="detection-top">
          <div className="detection-title">
            <h3 title={item.original_name}>{item.original_name}</h3>
            <p className="detection-meta">
              {formatTime(item.created_at)}
              {isImage ? ' · 图片' : ' · 视频'}
              {item.crop ? ` · ${item.crop}` : ''}
              {totalObjects > 0 ? ` · ${totalObjects} ${isImage ? '个检出目标' : '次跨帧检出'}` : ''}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flex: 'none' }}>
            <span className={`badge badge-${item.status}`}>
              {item.status === 'processing' || item.status === 'queued'
                ? <i className="badge-dot" />
                : null}
              {STATUS_TEXT[item.status] ?? item.status}
            </span>
            <button className="icon-btn" onClick={remove} aria-label="删除这条记录" title="删除">
              ✕
            </button>
          </div>
        </div>

        {/* ── 识别结果 ── */}
        {groups.length > 0 ? (
          <div className="pest-list">
            {groups.map((g) => (
              <div className="pest-row" key={g.name}>
                <div className="pest-line">
                  <span className="pest-name" title={g.nameEn}>
                    {g.name}
                    {g.name !== g.nameEn && <span className="pest-en">{g.nameEn}</span>}
                  </span>
                  <span className="pest-count">×{g.count}</span>
                </div>
                <div
                  className="conf-track"
                  role="progressbar"
                  aria-valuenow={Math.round(g.maxConf * 100)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${g.name} 最高置信度`}
                >
                  <div className="conf-fill" style={{ width: `${Math.round(g.maxConf * 100)}%` }} />
                </div>
                <span className="pest-avg">最高置信度 {Math.round(g.maxConf * 100)}%</span>
              </div>
            ))}
          </div>
        ) : item.status === 'completed' ? (
          <div className="no-pest">本次没有检测框</div>
        ) : null}

        {!isImage && item.video_meta && <p className="pest-avg">
          抽样检测 {String(item.video_meta.sampled_frames ?? 0)} 帧；跨帧检出次数不等于独立虫体数量。
          {item.video_meta.h264 === false ? ' 当前视频编码可能无法在浏览器播放。' : ''}
        </p>}
        {!isImage && item.status === 'completed' && <VideoTimeline
          events={item.predictions as { time_ms: number; detections: Prediction[] }[]}
          onSeek={(seconds) => { if (videoRef.current) { videoRef.current.currentTime = seconds; videoRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' }) } }}
        />}
        {isImage && preds.some((p) => p.prior) && <p className="pest-avg">
          已结合作物信息调整候选排序，进度条显示原始模型置信度。
        </p>}
        <ObservationTools item={item} onUpdated={onUpdated} onError={onError}/>
        <VideoProgress item={item} onUpdated={onUpdated} onError={onError}/>
        <AnalysisStatus item={item} onUpdated={onUpdated} onError={onError} />
        {/* ── AI 防治建议（含 RAG 溯源） ── */}
        {item.analysis && (
          <div className="advice">
            <button
              className="advice-head"
              onClick={() => setAdviceOpen((v) => !v)}
              aria-expanded={adviceOpen}
            >
              <b>AI 防治建议</b>
              {hasRefs && <span className="ref" style={{ cursor: 'default' }}>{item.references!.length}</span>}
              <span className="caret" aria-hidden="true">▼</span>
            </button>
            {adviceOpen && (
              <div className="advice-body">
                <div className="advice-text">{renderWithRefs(item.analysis, jumpToRef)}</div>

                {hasRefs && (
                  <>
                    <button
                      className="btn btn-sm btn-ghost"
                      onClick={() => setRefsOpen((v) => !v)}
                      aria-expanded={refsOpen}
                    >
                      {refsOpen ? '收起参考资料' : `查看 ${item.references!.length} 条参考资料`}
                    </button>
                    {refsOpen && (
                      <div className="refs fade-in">
                        {item.references!.map((r: Reference) => (
                          <div className="ref-item" key={r.ref} id={`ref-${item.id}-${r.ref}`}>
                            <div className="ref-item-head">
                              <span className="ref">{r.ref}</span>
                              <b>{r.title || r.id || '知识库条目'}</b>
                              {r.source && <span className="ref-src">{r.source}</span>}
                            </div>
                            {r.body && <p className="ref-body">{r.body}</p>}
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}

                <div className="vote">
                  <span className="pest-avg">这个建议有用吗？</span>
                  <button
                    className={`vote-btn${vote === 'good' ? ' active' : ''}`}
                    onClick={() => vote_('good')}
                    disabled={!!vote}
                  >👍 有用</button>
                  <button
                    className={`vote-btn${vote === 'bad' ? ' active' : ''}`}
                    onClick={() => vote_('bad')}
                    disabled={!!vote}
                  >👎 不准</button>
                  {vote && <span className="vote-done">已反馈，谢谢！</span>}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── 追问 ── */}
        {item.status === 'completed' && (
          <div className="chat">
            <button
              className="btn btn-sm btn-ghost"
              onClick={() => setChatOpen((v) => !v)}
              aria-expanded={chatOpen}
            >
              {chatOpen ? '收起追问' : '继续追问 AI'}
            </button>
            {chatOpen && (
              <div className="fade-in" style={{ display: 'grid', gap: '0.5rem' }}>
                <div className="chat-log" aria-live="polite">
                  {history.length === 0 && !chatBusy && (
                    <p className="chat-empty">可以问：还会传染哪些作物？用什么药？什么时候打最合适？</p>
                  )}
                  {history.map((m, i) => (
                    <div className={`chat-msg ${m.role}`} key={i}>
                      <span className="chat-avatar">{m.role === 'user' ? '我' : 'AI'}</span>
                      <div className="chat-bubble">{m.content}</div>
                    </div>
                  ))}
                  {chatBusy && (
                    <div className="chat-msg assistant">
                      <span className="chat-avatar">AI</span>
                      <div className="chat-bubble"><span className="spinner" /></div>
                    </div>
                  )}
                </div>
                <div className="chat-input-row">
                  <input
                    className="input"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
                    placeholder="输入你的问题（≤500 字）"
                    maxLength={500}
                    disabled={chatBusy}
                  />
                  <button className="btn btn-sm" onClick={send} disabled={chatBusy || !draft.trim()}>
                    发送
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </article>
  )
}

export type Observation = {field_name: string; growth_stage: string; severity: string; notes: string; correction: string}
export const emptyObservation: Observation = {field_name:'',growth_stage:'',severity:'',notes:'',correction:''}
export type Prediction = {
  class: string; class_cn?: string; confidence: number; bbox: Record<string, number>
  raw_confidence?: number; ranking_score?: number; is_primary?: boolean; is_suspect?: boolean
  prior?: { level: string; factor: number; crop_label: string; note: string }
}
export type Detection = {
  observation?: Observation | null; quality?: {width:number;height:number;warnings:string[];method:string} | null; feedback_note?: string | null;
  feedback?: 'good' | 'bad' | null;
  id: string; media_type: 'image' | 'video'; original_name: string;
  status: string; predictions: Prediction[] | { time_ms: number; detections: Prediction[] }[];
  progress?: {stage: string; processed_frames: number; total_frames: number; percent: number | null; can_retry: boolean} | null;
  crop?: string | null; video_meta?: Record<string, unknown> | null;
  result_url: string | null; analysis: string | null;
  analysis_status: 'queued' | 'processing' | 'completed' | 'failed' | 'disabled' | 'skipped';
  analysis_error: string | null;
  references?: Reference[] | null; error: string | null; created_at: string;
}
export type Reference = { ref: number; id?: string; title?: string; body?: string; source?: string }
export type ChatMessage = { role: string; content: string; created_at: string }
export type CropOption = { key: string; label: string; has_prior?: boolean }
export type Statistics = {
  total_jobs: number; image_jobs: number; video_jobs: number;
  completed_jobs: number; failed_jobs: number; total_objects: number;
  classes: { name: string; name_cn?: string; count: number }[];
}

const API_URL = import.meta.env.VITE_API_URL ?? '/api'

/** 会话过期信号：由调用方决定是跳登录还是提示重登 */
export class SessionExpiredError extends Error {
  constructor() {
    super('登录已过期，请重新登录')
    this.name = 'SessionExpiredError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('token')
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), init.body instanceof FormData ? 120_000 : 30_000)
  const abort = () => controller.abort()
  init.signal?.addEventListener('abort', abort, {once: true})
  if (init.signal?.aborted) controller.abort()
  try {
    const response = await fetch(`${API_URL}${path}`, {...init, headers, signal: controller.signal})
    if (response.status === 401) {
      localStorage.removeItem('token')
      throw new SessionExpiredError()
    }
    if (response.status === 204) return undefined as T
    let body
    try {body = await response.json()} catch (error) {
      if (controller.signal.aborted) throw error
      throw new Error('服务返回了无法读取的结果，请稍后重试')
    }
    if (!response.ok) {
      const detail = body?.detail
      throw new Error((typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : '') || `请求失败 (${response.status})`)
    }
    return body as T
  } catch (error) {
    if (init.signal?.aborted) throw error
    if (controller.signal.aborted) throw new Error('请求超时，请刷新记录确认处理结果')
    if (error instanceof TypeError) throw new Error('网络连接失败，请检查后端服务是否启动')
    throw error
  } finally {
    window.clearTimeout(timeout)
    init.signal?.removeEventListener('abort', abort)
  }
}

/** 统一错误信息：把后端的技术细节翻译成用户看得懂的话。

  注意匹配顺序：必须"具体 → 泛化"。
  之前 `'too large'` 排在 `'dimensions are too large'` 之前，
  而后者本身包含前者，导致"图片尺寸超限"这条规则**永远不可达**，
  尺寸问题一直被显示成笼统的"文件太大了"。 */
function friendly(err: unknown): string {
  if (err instanceof SessionExpiredError) return err.message
  const raw = err instanceof Error ? err.message : String(err ?? '')
  if (raw.includes('网络连接失败')) return raw
  // 具体规则在前
  if (raw.includes('dimensions are too large')) return '图片尺寸超出限制（最大 2500 万像素）'
  if (raw.includes('not a valid image')) return '文件已损坏或不是有效图片'
  if (raw.includes('not a valid video')) return '文件已损坏或不是有效视频'
  if (raw.includes('Image is too large') || raw.includes('Video is too large')
      || raw.includes('413')) return '文件太大了，请压缩后再试'
  if (raw.includes('415')) return '不支持的文件格式'
  if (raw.includes('422')) return raw
  if (raw.includes('503')) return 'AI 服务暂时不可用，请稍后再试'
  if (raw.includes('500')) return '服务器开小差了，请稍后重试'
  return raw || '操作失败，请重试'
}

export { friendly }

export async function register(username: string, password: string) {
  return request('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export async function login(username: string, password: string) {
  const body = new URLSearchParams({ username, password })
  const data = await request<{ access_token: string }>('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  localStorage.setItem('token', data.access_token)
}

export async function fetchMe() {
  return request<{ id: number; username?: string; email?: string }>('/auth/me')
}

/** 退出登录：通知服务端吊销这张令牌，再清掉本地副本。

  无论请求成败都必须清本地 —— 网络断了也得让用户能登出。 */
export async function logout() {
  try {
    await request<void>('/auth/logout', { method: 'POST' })
  } catch {
    /* 服务端吊销失败不阻塞本地登出 */
  }
  localStorage.removeItem('token')
  ticketCache.clear()
}

export const listDetections = (signal?: AbortSignal, mediaType?: string) => request<Detection[]>('/detections?limit=100'+(mediaType ? '&media_type='+encodeURIComponent(mediaType) : ''), {signal})
export const getDetection = (id: string) => request<Detection>(`/detections/${id}`)
export const listCrops = () =>
  request<{ available: boolean; error: string | null; crops: CropOption[] }>('/detections/crops')
export const fetchStatistics = () => request<Statistics>('/statistics')
export const fetchHealth = () => request<{ detector: 'mock' | 'yolo' | 'unavailable'; detector_ready: boolean }>('/health')

function upload(path: string, file: File, crop?: string, observation?: Observation, progress?: (value:number)=>void) {
  return new Promise<Detection>((resolve,reject)=>{
    const xhr=new XMLHttpRequest(), body=new FormData()
    body.append('file',file)
    if(crop) body.append('crop',crop)
    if(observation) body.append('observation',JSON.stringify(observation))
    xhr.open('POST',API_URL+path);xhr.timeout=120000
    const token=localStorage.getItem('token')
    if(token) xhr.setRequestHeader('Authorization','Bearer '+token)
    xhr.upload.onprogress=e=>{if(e.lengthComputable)progress?.(Math.round(e.loaded/e.total*100))}
    xhr.onerror=()=>reject(new Error('上传连接中断，请先查看历史记录，再决定是否重试'))
    xhr.ontimeout=()=>reject(new Error('上传请求超时，请先查看历史记录确认是否已收到'))
    xhr.onload=()=>{
      if(xhr.status===401){localStorage.removeItem('token');reject(new SessionExpiredError());return}
      try {const data=JSON.parse(xhr.responseText)
        if(xhr.status>=200&&xhr.status<300)resolve(data)
        else reject(new Error(typeof data.detail==='string'?data.detail:`上传失败 (${xhr.status})`))
      }catch{reject(new Error('无法读取上传结果，请查看历史记录后重试'))}
    }
    xhr.send(body)
  })
}
export const uploadImage=(file:File,crop?:string,observation?:Observation,progress?:(v:number)=>void)=>upload('/detections/image',file,crop,observation,progress)
export const uploadVideo=(file:File,crop?:string,observation?:Observation,progress?:(v:number)=>void)=>upload('/videos',file,crop,observation,progress)
export const saveObservation=(id:string,body:Observation)=>request<Detection>(`/detections/${id}/observation`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
export const refreshAdvice=(id:string)=>request<Detection>(`/detections/${id}/analysis?refresh=true`,{method:'POST'})
export async function originalImage(id:string):Promise<Blob> {
  const response=await fetch(`${API_URL}/detections/${id}/original`,{headers:{Authorization:'Bearer '+localStorage.getItem('token')},signal:AbortSignal.timeout(30000)})
  if(response.status===401){localStorage.removeItem('token');throw new SessionExpiredError()}
  if(!response.ok)throw new Error(response.status===410?'原图已被清理':'原图加载失败')
  return response.blob()
}

export const deleteDetection = (id: string) => request(`/detections/${id}`, { method: 'DELETE' })
export const deleteAllDetections = () => request('/detections/all', { method: 'DELETE' })
export const retryAnalysis = (id: string) => request<Detection>(`/detections/${id}/analysis`, { method: 'POST' })

/* ── 结果文件访问 ──────────────────────────────────────────────────────
   以前是把 JWT 直接拼进 URL（`?token=<JWT>`）给 <img>/<video> 用。
   那等于把 12 小时有效、全权代表用户的凭据写进浏览器历史、Referer
   和 nginx 访问日志。现在改为：先调 /result-ticket 换一张绑定到
   该 detection 的 5 分钟 HMAC 票据，URL 里只有一个短时签名。 */

type Ticket = { url: string; expiresAt: number }
const ticketCache = new Map<string, Ticket>()

/** 提前 30 秒视为过期，避免刚好卡在边界上被拒。 */
const TICKET_SKEW_MS = 30_000

export async function getResultUrl(detectionId: string): Promise<string | null> {
  const cached = ticketCache.get(detectionId)
  if (cached && cached.expiresAt - TICKET_SKEW_MS > Date.now()) {
    return `${API_URL}${cached.url.replace('/api', '')}`
  }
  try {
    const r = await request<{ url: string; expires_in: number }>(
      `/detections/${detectionId}/result-ticket`,
    )
    ticketCache.set(detectionId, {
      url: r.url,
      expiresAt: Date.now() + r.expires_in * 1000,
    })
    return `${API_URL}${r.url.replace('/api', '')}`
  } catch (error) {
    if (error instanceof SessionExpiredError) throw error
    return null
  }
}

/** 记录被删除时清掉缓存，避免留下无主条目。 */
export function forgetResultUrl(detectionId: string): void {
  ticketCache.delete(detectionId)
}

/* ── 多轮追问 ── */
export const sendChat = (detectionId: string, message: string) =>
  request<{ reply: string }>(`/detections/${detectionId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })

export const getChatHistory = (detectionId: string) =>
  request<ChatMessage[]>(`/detections/${detectionId}/chat`)

/* ── 结果反馈 ── */
export const submitFeedback = (detectionId: string, rating: 'good' | 'bad', note?: string) =>
  request<{ ok: boolean }>(`/detections/${detectionId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(note ? { rating, note } : { rating }),
  })

export type RecordFilters = {detection_id?: string; field_name?: string; offset: number; limit: number; media_type?: string; status?: string; q?: string; start_at?: string; end_at?: string}
export type RecordPage = {items: Detection[]; total: number; offset: number; limit: number}
export function searchDetections(filters: RecordFilters, signal?: AbortSignal) {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key,value]) => {if (value !== undefined && value !== '') query.set(key,String(value))})
  return request<RecordPage>('/detections/search?'+query, {signal})
}
export const retryVideo = (id: string) => request<Detection>(`/videos/${encodeURIComponent(id)}/retry`, {method:'POST'})

export type Comparison = {id:string;title:string;symptoms:string;source:string;detected:boolean}
export const comparePests=(id:string)=>request<Comparison[]>(`/detections/${id}/comparison`)

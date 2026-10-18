const $ = id => document.getElementById(id);
const PAGE_NAME = document.body.dataset.page;
function loginPath() { return '/login?next=' + encodeURIComponent(location.pathname); }
function safeReturnPath() {
 const next=new URLSearchParams(location.search).get('next');
 return ['/detect','/video','/history','/statistics','/features','/about','/contact','/model','/deployment','/'].includes(next) ? next : '/';
}
function analysisBlock(it) {
  if (it.analysis) return '<b>💡 AI 防治建议</b><br>' + renderWithRefs(it.analysis, it.references) + refsBlock(it.references);
  const state = it.analysis_status;
  if (state === 'queued' || state === 'processing') return '识别结果已保存，AI 防治建议正在生成…';
  if (state === 'failed') return esc(it.analysis_error || '建议生成失败，识别结果已保留') + ' <button onclick="retryAdvice(\'' + it.id + '\')">重试建议</button>';
  if (state === 'disabled') return '尚未配置 AI 服务；识别结果已保存，可在后台配置 AI 服务后重试。 <button onclick="retryAdvice(\'' + it.id + '\')">重试建议</button>';
  if (it.status !== 'completed') return '识别完成后可查看建议。';
  return '本次未检出目标，请结合田间观察判断，必要时换角度补拍。';
}
async function retryAdvice(id) {
  try { await api('/detections/' + id + '/analysis', {method:'POST'}); pollRounds = 0; await refreshAll(); }
  catch(e) { toast(e.message, false); }
}
let currentDetectionId = null;
let pollTimer = null;
let pollRounds = 0;
const MAX_POLL_ROUNDS = 40;   // 3s × 40 = 2 分钟，超过就停止并提示检查 Worker
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// ===== RAG 溯源渲染 =====
// 把正文里的 [1][2] 渲染成可点击角标。只有 references 里真实存在的编号才渲染成角标，
// 模型若编造了资料里没有的编号，就保持纯文本——不替它伪造一个「可溯源」的假象。
function renderWithRefs(text, refs) {
  const valid = new Set((refs || []).map(r => Number(r.ref)));
  return esc(text).replace(/\n/g, '<br>').replace(/\[(\d+)\]/g, (m, n) =>
    valid.has(Number(n)) ? `<sup class="ref" data-ref="${n}">${n}</sup>` : m
  );
}

function refsBlock(refs) {
  if (!refs || !refs.length) return '';
  return `<details class="refs"><summary>参考资料 ${refs.length} 条 · 结论可溯源</summary>`
    + refs.map(r => `<div class="ref-item" data-refn="${esc(r.ref)}">
         <div class="ref-h">[${esc(r.ref)}] ${esc(r.title)}</div>
         <div class="ref-s">来源：${esc(r.source)}</div>
         <div class="ref-b">${esc(r.body)}</div>
       </div>`).join('')
    + '</details>';
}

// 点角标 → 展开所属卡片的资料列表并高亮对应条目。
// 用 closest 限定在卡片内查找，避免页面上多张卡片都有 [1] 时跳错位置。
document.addEventListener('click', e => {
  const sup = e.target.closest && e.target.closest('sup.ref');
  if (!sup) return;
  const n = sup.dataset.ref;
  const box = sup.closest('.hbody') || sup.closest('.cbody') || sup.closest('#advice') || document;
  const d = box.querySelector('details.refs');
  if (d) d.open = true;
  const item = box.querySelector(`.ref-item[data-refn="${n}"]`);
  if (!item) return;
  item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  item.classList.add('hl');
  setTimeout(() => item.classList.remove('hl'), 1800);
});


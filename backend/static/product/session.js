// ── 结果文件的短时票据 ──────────────────────────────────────────────
// 以前是 <img src="...result?token=<JWT>">，把 12 小时有效的会话凭据
// 写进 URL —— 于是它会进浏览器历史、Referer 和 nginx 访问日志。
// 现在改成先换一张 5 分钟、且只对单条 detection 有效的 HMAC 票据。
const _ticketCache = new Map();

function _detectionIdOf(resultUrl) {
  const m = /\/(?:api\/)?detections\/([^/]+)\/result/.exec(resultUrl || '');
  return m ? m[1] : null;
}

async function fetchResultTicket(detectionId) {
  const hit = _ticketCache.get(detectionId);
  if (hit && hit.expiresAt - 30000 > Date.now()) return hit.url;
  const r = await api('/detections/' + encodeURIComponent(detectionId) + '/result-ticket');
  if (!r || !r.url) return null;
  _ticketCache.set(detectionId, {
    url: r.url,
    expiresAt: Date.now() + (r.expires_in || 300) * 1000,
  });
  return r.url;
}

// 同步读取：渲染历史列表时用。取不到就返回 null，由调用方显示占位。
function resultUrl(item, fallbackPath) {
  const id = item && item.id ? item.id : _detectionIdOf(fallbackPath);
  const hit = id ? _ticketCache.get(id) : null;
  if (hit && hit.expiresAt - 30000 > Date.now()) return hit.url;
  return null;
}

// 渲染前把这一批要显示的记录都换成票据（并发，失败不影响其他条目）
async function warmResultTickets(rows) {
  const wanted = rows
    .filter(it => it.status === 'completed' && it.result_url && it.id)
    .map(it => it.id);
  await Promise.all(wanted.map(id => fetchResultTicket(id).catch(() => null)));
}

function softLogout(msg) {  localStorage.removeItem('token');
  currentUser = null;
  setGuestNav();
  const c = $('authCard');
  if (c) { c.style.display = 'block'; }
  if (msg && $('authMsg')) showMsg('authMsg', msg, false);
  if (PAGE_NAME !== 'login') location.replace(loginPath());
  else document.documentElement.removeAttribute('data-session-pending');
}

// 顶栏按登录态切换：游客 → 「免费试用」；已登录 → 「账号 + 退出登录」
let currentUser = null;
function setGuestNav() {
  const t = $('topCta'), u = $('navUser');
  if (t) { t.style.display = ''; t.textContent = '免费试用'; }
  if (u) u.style.display = 'none';
}
function setUserNav(name) {
  const t = $('topCta'), u = $('navUser'), w = $('navWho');
  if (t) t.style.display = 'none';
  if (w) w.textContent = name ? ('🌿 ' + name) : '🌿 已登录';
  if (u) u.style.display = 'flex';
}

let toastTimer = null;
function toast(text, ok) {
  let el = $('pgToast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'pgToast'; el.className = 'pg-toast';
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.style.background = ok ? 'rgba(4,120,87,.95)' : 'rgba(12,31,23,.94)';
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), ok ? 2600 : 4200);
}

// 退出登录：先让服务端吊销 token（jti 进黑名单），再清本地态。
// 服务端失败也要继续清本地 —— 否则用户会被永久卡在当前账号里出不去。
async function doLogout() {
  const btn = $('logoutBtn');
  if (btn) { btn.disabled = true; btn.textContent = '退出中…'; }
  try {
    await api('/auth/logout', { method: 'POST' });
  } catch (e) {
    console.warn('服务端注销失败，已按本地退出处理', e);
  }
  localStorage.removeItem('token');
  currentUser = null;
  // 整页重载是最彻底的状态清理：历史记录、统计、标注图、作物选择
  // 都是上一个账号的数据，手写 reset 漏一项就会串号。
  try { sessionStorage.setItem('pg_just_logout', '1'); } catch (e) {}
  location.reload();
}

function showMsg(id, text, ok) {
  const el = $(id); el.textContent = text; el.className = 'msg ' + (ok ? 'ok' : 'err');
}

// ===== 上传图片：真填到控制台 =====
// 上传前先在本地挡一道：选错类型或超大文件不用等几十秒才被服务端 413/415 打回来
// 上传类操作的登录前置检查：游客点上传会一路打到后端拿到 401，softLogout 又把
// 提示写成「登录已过期」——对从没登录过的人是误导。这里在本地先拦一道，
// 直接把用户带到登录卡片并给出正确话术。
function requireLogin() {
  if (localStorage.getItem('token')) return true;
  location.assign(loginPath());
  return false;
}


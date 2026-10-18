// 「立即登录体验」原本直接 scrollIntoView，但已登录时 authCard 是 display:none，
// 会滚到一片空白。这里按登录态分流：已登录引导到控制台，未登录先显示卡片再滚动并聚焦。
function openAuthCard() {
 if (PAGE_NAME !== 'login') { location.assign(localStorage.getItem('token') ? '/detect' : loginPath()); return; }
 const card=$('authCard'); card.style.display='block'; $('username').focus();
}

// 弹窗 DOM 在主脚本之后解析，所以这里用 document 委托，避免脚本执行时取不到节点
document.addEventListener('click', e => {
  if (e.target && e.target.id === 'infoModal') closeInfo();
});
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  const m = $('infoModal');
  if (m && m.style.display === 'flex') closeInfo();
  const c = document.getElementById('camModal');
  if (c && c.style.display === 'flex') closeCamera();
});

// ===== 鉴权 =====
// 两种模式共用同一个表单：显式记录当前模式，并让两个按钮都有明确的选中态，
// 避免旧版「点了注册但界面上只有一个按钮的文字变了」引起的误操作
let authMode = 'login';   // 'login' | 'register'

function setAuthMode(mode) {
  authMode = mode;
  const isReg = mode === 'register';
  $('loginBtn').textContent = isReg ? '注册并登录' : '登录';
  $('regBtn').textContent = isReg ? '返回登录' : '注册新账号';
  $('loginBtn').classList.toggle('primary', !isReg);
  $('loginBtn').classList.toggle('ghost', isReg);
  $('regBtn').classList.toggle('primary', isReg);
  $('regBtn').classList.toggle('ghost', !isReg);
  $('authTip').textContent = isReg
    ? '账号 3-32 位字母/数字/下划线，密码至少 6 位。注册成功后会自动登录。'
    : '还没有账号？点右边「注册新账号」即可，账号随便取，不用填邮箱。';
  const m = $('authMsg'); m.className = 'auth-msg'; m.textContent = '';
}

if ($('regBtn')) $('regBtn').onclick = () => setAuthMode(authMode === 'register' ? 'login' : 'register');

if ($('authForm')) $('authForm').onsubmit = async (e) => {
  e.preventDefault();
  const username = $('username').value.trim();
  const password = $('password').value;
  const msg = $('authMsg');
  try {
    if (authMode === 'register') {
      await api('/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      msg.textContent = '注册成功，正在登录…';
      msg.className = 'auth-msg ok';
    }
    const tok = await api('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username, password }),
    });
    localStorage.setItem('token', tok.access_token);
    const u = tok && tok.user;
    enterApp(u ? (u.username || u.email || null) : null);
    toast('登录成功，欢迎回来', true);
  } catch (err) {
    msg.textContent = err.message;
    msg.className = 'auth-msg err';
  }
};
$('topCta').onclick = openAuthCard;
if ($('logoutBtn')) $('logoutBtn').onclick = doLogout;

if ($('imgFile')) $('imgFile').onchange = e => e.target.files[0] && uploadImage(e.target.files[0]);
if ($('vidFile')) $('vidFile').onchange = e => e.target.files[0] && uploadVideo(e.target.files[0]);

function enterApp(name) {
  document.documentElement.removeAttribute('data-session-pending');
  if (PAGE_NAME === 'login') { location.replace(safeReturnPath()); return; }
  if ($('authCard')) $('authCard').style.display = 'none';
  if (name) currentUser = name;
  setUserNav(currentUser);
  // 登录后才有权限拉作物清单（接口需鉴权），所以放在这里而不是启动时
  loadCrops();
  refreshAll();
}

// 滚动导航加实
window.addEventListener('scroll', () => { $('nav').classList.toggle('solid', window.scrollY > 40); });

// 渐显
const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold:.18 });
document.querySelectorAll('.reveal').forEach(el => io.observe(el));

function showGuest() {
  if (PAGE_NAME !== 'login') { location.replace(loginPath()); return; }
  document.documentElement.removeAttribute('data-session-pending');
  setGuestNav();
  if ($('authCard')) $('authCard').style.display = 'block';
  // 游客态不请求接口（必然 401，还会触发一次「登录已过期」的误导提示），
  // 直接给引导占位：「数据表现」「检测案例」原来只有标题、内容全空。
  renderStatsPlaceholder('登录后即可查看你的累计识别统计与虫种分布');
  if ($('emptyTip')) { $('emptyTip').textContent = '登录后即可查看历史检测记录'; $('emptyTip').style.display = 'block'; }
  if ($('loginNote')) $('loginNote').hidden = false;
  // 游客态的下拉框文案要自己说清楚，不能停在「加载中…」
  loadCrops();
}

// 启动
if (localStorage.getItem('token')) {
  // 刷新后顶栏要显示账号名，得先问一次 /auth/me；
  // token 过期时这里会 401，softLogout 会把人带回登录卡片，不会卡在半登录状态。
  api('/auth/me')
    .then(u => enterApp(u ? (u.username || u.email || null) : null))
    .catch(() => softLogout('登录已过期，请重新登录'));
} else {
  showGuest();
  // 刚退出登录：把人送到登录卡片并说明可以换号，避免「退出了但不知道下一步」
  let justOut = false;
  try { justOut = sessionStorage.getItem('pg_just_logout') === '1'; sessionStorage.removeItem('pg_just_logout'); } catch (e) {}
  if (justOut && $('authMsg')) {
    showMsg('authMsg', '已退出登录，可以换一个账号登录了', true);
    setTimeout(() => { const u = $('username'); if (u) u.focus({ preventScroll: true }); }, 200);
  }
}

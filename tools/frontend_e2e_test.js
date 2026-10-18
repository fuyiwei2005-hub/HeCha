// 用真实 Edge 跑一遍：注册A → 登录A → 退出 → 注册B → 登录B → 摄像头按钮状态
const { spawn } = require('child_process');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9333;
const URL = process.argv[2] || 'http://127.0.0.1:8010/';
const sleep = ms => new Promise(r => setTimeout(r, ms));

let id = 0, pending = new Map(), ws;
function send(method, params = {}) {
  const i = ++id;
  ws.send(JSON.stringify({ id: i, method, params }));
  return new Promise(r => pending.set(i, r));
}
async function evalJs(expr) {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, allowUnsafeEvalBlockedByCSP: true });
  if (r.result && r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400));
  return r.result ? r.result.result.value : undefined;
}
const ok = (n, c, extra = '') => console.log(`${c ? 'PASS' : 'FAIL'}  ${n}${extra ? '  | ' + extra : ''}`);

(async () => {
  const proc = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--mute-audio',
    `--remote-debugging-port=${PORT}`, '--user-data-dir=C:\\Windows\\Temp\\cdp_pg_' + Date.now(),
    URL,
  ], { stdio: 'ignore' });

  // 拿 ws 地址：json/list 第一个可能是扩展的后台页，必须挑真正的页面标签
  let target = null;
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const list = await r.json();
      target = list.find(t => t.type === 'page' && /^https?:/.test(t.url || ''));
      if (target) break;
    } catch (e) {}
    await sleep(400);
  }
  if (!target) { console.log('FAIL  无法连接 Edge'); proc.kill(); process.exit(1); }
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
  await send('Page.enable'); await send('Runtime.enable');

  await sleep(4500);
  console.log('INFO  页面: ' + await evalJs('document.title'));

  // ---------- 1. 注册并登录账号 A ----------
  const ua = 'cdp_a' + Date.now().toString().slice(-5);
  await evalJs(`
    (function(){
      setAuthMode('register');
      document.getElementById('username').value = ${JSON.stringify(ua)};
      document.getElementById('password').value = 'abc123456';
      document.getElementById('authForm').requestSubmit();
    })();
  `);
  await sleep(3000);
  let s = await evalJs(`JSON.stringify({
    who: (document.getElementById('navWho')||{}).textContent,
    navUserShown: getComputedStyle(document.getElementById('navUser')).display,
    ctaShown: getComputedStyle(document.getElementById('topCta')).display,
    authShown: getComputedStyle(document.getElementById('authCard')).display,
    token: !!localStorage.getItem('token')
  })`);
  s = JSON.parse(s);
  ok('注册账号A后自动登录', s.token && s.navUserShown === 'flex' && s.authShown === 'none', JSON.stringify(s));
  ok('顶栏显示账号A', (s.who || '').includes(ua), s.who);

  // ---------- 2. 退出登录 ----------
  await evalJs(`document.getElementById('logoutBtn').click();`);
  await sleep(3500);
  s = JSON.parse(await evalJs(`JSON.stringify({
    token: !!localStorage.getItem('token'),
    authShown: getComputedStyle(document.getElementById('authCard')).display,
    navUserShown: getComputedStyle(document.getElementById('navUser')).display,
    ctaShown: getComputedStyle(document.getElementById('topCta')).display,
    msg: (document.getElementById('authMsg')||{}).textContent
  })`));
  ok('退出后 token 已清除', s.token === false, JSON.stringify(s));
  ok('退出后回到登录卡片', s.authShown === 'block' && s.navUserShown === 'none' && s.ctaShown !== 'none', s.msg);
  ok('退出后有换号提示', (s.msg || '').includes('换一个账号'), s.msg);

  // ---------- 3. 换账号 B 登录 ----------
  const ub = 'cdp_b' + Date.now().toString().slice(-5);
  await evalJs(`
    (function(){
      setAuthMode('register');
      document.getElementById('username').value = ${JSON.stringify(ub)};
      document.getElementById('password').value = 'abc123456';
      document.getElementById('authForm').requestSubmit();
    })();
  `);
  await sleep(3000);
  s = JSON.parse(await evalJs(`JSON.stringify({
    who: (document.getElementById('navWho')||{}).textContent,
    navUserShown: getComputedStyle(document.getElementById('navUser')).display,
    histText: (document.getElementById('emptyTip')||{}).textContent,
    histShown: getComputedStyle(document.getElementById('emptyTip')).display
  })`));
  ok('换账号B登录成功', s.navUserShown === 'flex' && (s.who || '').includes(ub), s.who);
  ok('新账号历史为空（不串号）', s.histShown === 'block', s.histText);

  // ---------- 4. 刷新后仍显示账号 ----------
  await send('Page.navigate', { url: URL });
  await sleep(3500);
  s = JSON.parse(await evalJs(`JSON.stringify({
    who: (document.getElementById('navWho')||{}).textContent,
    navUserShown: getComputedStyle(document.getElementById('navUser')).display
  })`));
  ok('刷新后顶栏仍显示账号B', s.navUserShown === 'flex' && (s.who || '').includes(ub), s.who);

  // ---------- 5. 摄像头按钮 ----------
  s = JSON.parse(await evalJs(`JSON.stringify({
    secure: window.isSecureContext,
    hasMedia: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
    disabled: document.getElementById('camBtn').disabled,
    text: document.getElementById('camBtn').textContent,
    title: document.getElementById('camBtn').title
  })`));
  console.log('INFO  摄像头能力: ' + JSON.stringify(s));
  ok('摄像头按钮状态与能力一致', s.secure && s.hasMedia ? !s.disabled : s.disabled, s.text);

  // 摄像头弹窗打开/关闭（有设备才会真出画面，这里只验证不抛英文报错）
  await evalJs(`document.getElementById('camBtn').click();`);
  await sleep(2500);
  s = JSON.parse(await evalJs(`JSON.stringify({
    modal: getComputedStyle(document.getElementById('camModal')).display,
    toast: (document.getElementById('pgToast')||{}).textContent || ''
  })`));
  console.log('INFO  拍照弹窗: ' + JSON.stringify(s));

  ws.close(); proc.kill();
  console.log('DONE');
  process.exit(0);
})().catch(e => { console.log('ERROR ' + e.message); process.exit(1); });

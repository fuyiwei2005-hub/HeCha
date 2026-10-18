/* 给每个候选界面截一张"已登录 + 真实检测结果"的图，便于横向比较。
   用法: node tools/shoot_variants.js <账号> <密码> [宽度]
*/
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const BASE = 'http://127.0.0.1:8000';
const USER = process.argv[2] || 'uidemo';
const PASS = process.argv[3] || 'uidemo@2026';
const WIDTH = Number(process.argv[4] || 1440);
const OUT = path.join(__dirname, '..');
const VARIANTS = ['v1', 'v2', 'v3', 'v4'];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function shootWith(port, variant) {
  const prof = path.join(process.env.TEMP, 'edgev_' + Math.random().toString(36).slice(2, 8));
  const edge = spawn(EDGE, [
    `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`,
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', 'about:blank',
  ], { stdio: 'ignore' });

  let t = null;
  for (let i = 0; i < 50; i++) {
    await sleep(400);
    try {
      t = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((x) => x.type === 'page');
      if (t) break;
    } catch {}
  }
  if (!t) { edge.kill(); throw new Error('CDP 未就绪 ' + variant); }

  const ws = new WebSocket(t.webSocketDebuggerUrl);
  let id = 0; const pend = new Map();
  ws.onmessage = (m) => { const j = JSON.parse(m.data); if (j.id && pend.has(j.id)) { pend.get(j.id)(j); pend.delete(j.id); } };
  await new Promise((r) => { ws.onopen = r; });
  const send = (m, p = {}) => new Promise((res) => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
  const ev = async (e) => (await send('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true })).result?.result?.value;

  await send('Emulation.setDeviceMetricsOverride', {
    width: WIDTH, height: 1000, deviceScaleFactor: 1, mobile: WIDTH < 600,
  });
  await send('Page.enable');
  await send('Page.navigate', { url: `${BASE}/${variant}` });
  await sleep(2600);

  // 登录
  const ok = await ev(`(async()=>{
    const r = await fetch('/api/auth/login',{method:'POST',
      headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:new URLSearchParams({username:${JSON.stringify(USER)},password:${JSON.stringify(PASS)}})});
    if(!r.ok) return 'fail';
    const j = await r.json();
    localStorage.setItem('pg_token', j.access_token);
    return 'ok';
  })()`);
  if (ok !== 'ok') { console.log(variant, '登录失败'); }

  await send('Page.navigate', { url: `${BASE}/${variant}` });
  await sleep(3200);

  // 打开最近一条结果
  await ev(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='查看结果');if(b)b.click();return !!b;})()`);
  await sleep(2600);

  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  const file = path.join(OUT, `_ui_${variant}${WIDTH < 600 ? '_m' : ''}.png`);
  fs.writeFileSync(file, Buffer.from(shot.result.data, 'base64'));
  const h = await ev(`document.documentElement.scrollHeight`);
  console.log(`${variant}  ${(fs.statSync(file).size / 1024).toFixed(0)} KB  高度 ${h}px  -> ${path.basename(file)}`);

  ws.close(); edge.kill(); await sleep(300);
  try { fs.rmSync(prof, { recursive: true, force: true }); } catch {}
}

(async () => {
  let port = 9500;
  for (const v of VARIANTS) { await shootWith(port++, v); }
  if (process.argv[5] === 'mobile') {
    for (const v of VARIANTS) { await shootWith(port++, v); }
  }
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });

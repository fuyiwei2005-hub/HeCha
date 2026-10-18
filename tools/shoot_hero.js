/* 只看首屏：给四版各截一张 1400×980 的顶部画面，用于横向对比。
   用法: node tools/shoot_hero.js <账号> <密码>
*/
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const BASE = 'http://127.0.0.1:8000';
const USER = process.argv[2] || 'uidemo';
const PASS = process.argv[3] || 'uidemo@2026';
const W = 1400, H = 980;
const OUT = path.join(__dirname, '..', 'docs', '界面候选');
const VARIANTS = ['v1', 'v2', 'v3', 'v4'];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function shoot(port, variant) {
  const prof = path.join(process.env.TEMP, 'edgeh_' + Math.random().toString(36).slice(2, 8));
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
  if (!t) { edge.kill(); throw new Error('CDP ' + variant); }

  const ws = new WebSocket(t.webSocketDebuggerUrl);
  let id = 0; const pend = new Map();
  ws.onmessage = (m) => { const j = JSON.parse(m.data); if (j.id && pend.has(j.id)) { pend.get(j.id)(j); pend.delete(j.id); } };
  await new Promise((r) => { ws.onopen = r; });
  const send = (m, p = {}) => new Promise((res) => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
  const ev = async (e) => (await send('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true })).result?.result?.value;

  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send('Page.enable');
  await send('Page.navigate', { url: `${BASE}/${variant}` });
  await sleep(2500);
  await ev(`(async()=>{const r=await fetch('/api/auth/login',{method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:new URLSearchParams({username:${JSON.stringify(USER)},password:${JSON.stringify(PASS)}})});
    const j=await r.json();localStorage.setItem('pg_token',j.access_token);return 'ok';})()`);
  await send('Page.navigate', { url: `${BASE}/${variant}` });
  await sleep(3600);
  // 打开最近一条结果，让右侧有内容
  await ev(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='查看结果');if(b)b.click();return !!b;})()`);
  await sleep(2800);
  await ev(`window.scrollTo(0,0)`);
  await sleep(400);

  const file = path.join(OUT, `首屏_${variant}.png`);
  const shot = await send('Page.captureScreenshot', { format: 'png' });   // 不给 beyondViewport => 只截图视口
  fs.writeFileSync(file, Buffer.from(shot.result.data, 'base64'));
  console.log(`${variant}  ${(fs.statSync(file).size / 1024).toFixed(0)} KB -> 首屏_${variant}.png`);

  ws.close(); edge.kill(); await sleep(300);
  try { fs.rmSync(prof, { recursive: true, force: true }); } catch {}
}

(async () => {
  let port = 9600;
  for (const v of VARIANTS) await shoot(port++, v);
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });

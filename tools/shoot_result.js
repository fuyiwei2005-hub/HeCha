/* 截"结果区"：滚动到识别结果卡片，只截视口，用于对比建议文本的排版差异。
   用法: node tools/shoot_result.js <账号> <密码>
*/
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const BASE = 'http://127.0.0.1:8000';
const USER = process.argv[2] || 'uidemo';
const PASS = process.argv[3] || 'uidemo@2026';
const W = Number(process.argv[4] || 1400), H = Number(process.argv[5] || 1040);
const OUT = path.join(__dirname, '..', 'docs', '界面候选');
const VARIANTS = ['v1', 'v2', 'v3', 'v4'];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function shoot(port, variant) {
  const prof = path.join(process.env.TEMP, 'edger_' + Math.random().toString(36).slice(2, 8));
  const edge = spawn(EDGE, [
    `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`,
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', 'about:blank',
  ], { stdio: 'ignore' });

  let t = null;
  for (let i = 0; i < 50; i++) {
    await sleep(400);
    try { t = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((x) => x.type === 'page'); if (t) break; } catch {}
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
  await ev(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='查看结果');if(b)b.click();return !!b;})()`);
  await sleep(3000);

  // 滚到"防治建议"标题
  const y = await ev(`
    (()=>{
      const h = [...document.querySelectorAll('h3')].find(n=>n.textContent.includes('防治建议'));
      if(!h) return -1;
      const top = h.getBoundingClientRect().top + window.scrollY - 130;
      window.scrollTo(0, Math.max(0, top));
      return Math.round(top);
    })()
  `);
  await sleep(700);
  const file = path.join(OUT, `建议_${variant}.png`);
  const shot = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(file, Buffer.from(shot.result.data, 'base64'));
  console.log(`${variant}  滚动到 y=${y}  ${(fs.statSync(file).size / 1024).toFixed(0)} KB -> 建议_${variant}.png`);

  ws.close(); edge.kill(); await sleep(300);
  try { fs.rmSync(prof, { recursive: true, force: true }); } catch {}
}

(async () => {
  let port = 9700;
  for (const v of VARIANTS) await shoot(port++, v);
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });

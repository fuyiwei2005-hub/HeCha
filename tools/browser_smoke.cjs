// Run against the isolated tools/smoke_app.py server. No paid API or real model.
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const assert = require('assert/strict');
const playwrightModule = process.env.PESTGUARD_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'output', 'browser-smoke');
fs.mkdirSync(output, { recursive: true });
const port = 8137;
const base = `http://127.0.0.1:${port}`;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const python = path.join(root, '.venv', 'Scripts', 'python.exe');
  const log = fs.openSync(path.join(output, 'server.log'), 'w');
  const server = spawn(python, [path.join(__dirname, 'smoke_app.py'), String(port)], {
    cwd: root, windowsHide: true, stdio: ['ignore', log, log],
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUNBUFFERED: '1' },
  });
  let browser;
  const checks = [];
  const errors = [];
  try {
    for (let i = 0; i < 100; i++) {
      if (server.exitCode !== null) throw new Error('Smoke server exited; see output/browser-smoke/server.log');
      try { if ((await fetch(base + '/api/health')).ok) break; } catch {}
      await pause(200);
    }
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base);
    await page.getByRole('button', { name: '没有账号？去注册' }).click();
    await page.getByLabel('账号', { exact: true }).fill('smoke_' + Date.now());
    await page.getByLabel('密码', { exact: true }).fill('Smoke-password-123');
    await page.getByRole('button', { name: '注册并登录' }).click();
    await page.getByRole('button', { name: '选择图片', exact: true }).waitFor();
    checks.push('registration and login');

    const imagePath = path.join(output, 'synthetic.png');
    const videoPath = path.join(output, 'synthetic.mp4');
    const makeFixtures = spawn(python, ['-c',
      "from PIL import Image; import cv2,numpy as np,sys; Image.new('RGB',(64,64),'green').save(sys.argv[1]); w=cv2.VideoWriter(sys.argv[2],cv2.VideoWriter_fourcc(*'mp4v'),10,(64,64)); [w.write(np.zeros((64,64,3),dtype=np.uint8)) for _ in range(10)]; w.release()",
      imagePath, videoPath], { windowsHide: true });
    await new Promise((resolve, reject) => makeFixtures.on('exit', code => code === 0 ? resolve() : reject(new Error('fixture creation failed'))));
    await page.locator('input[type=file]').first().setInputFiles(imagePath);
    await page.getByText('重试建议', { exact: true }).waitFor({ timeout: 20000 });
    assert(await page.locator('.detection img').count() === 1);
    checks.push('image result survives advice failure');
    await page.getByRole('button', { name: '重试建议', exact: true }).click();
    await page.getByText('这是浏览器集成测试的模拟防治建议。', { exact: false }).waitFor({ timeout: 20000 });
    await page.getByRole('button', { name: /查看 1 条参考资料/ }).click();
    await page.getByText('集成测试参考条目', { exact: true }).waitFor();
    checks.push('advice retry and source references');
    await page.getByRole('button', { name: '继续追问 AI', exact: true }).click();
    await page.getByPlaceholder('输入你的问题（≤500 字）').fill('这是测试问题');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await page.getByText('这是集成测试的模拟追问回答。', { exact: true }).waitFor();
    checks.push('follow-up chat');
    await page.getByRole('button', { name: '👍 有用', exact: true }).click();
    await page.getByText('已反馈，谢谢！').waitFor();
    checks.push('feedback');
    await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true });

    await page.locator('input[type=file]').nth(1).setInputFiles(videoPath);
    await page.getByRole('button', { name: /查看 .* 个检出时间点/ }).waitFor({ timeout: 30000 });
    await page.getByRole('button', { name: /查看 .* 个检出时间点/ }).click();
    await page.locator('.timeline-event').first().waitFor();
    checks.push('video processing, polling and timeline');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'mobile horizontal overflow');
    checks.push('mobile layout');
    page.on('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: '清空记录', exact: true }).click();
    await page.getByText('还没有检测记录', { exact: true }).waitFor();
    checks.push('clear records');
    await page.getByRole('button', { name: '退出', exact: true }).click();
    await page.getByRole('button', { name: '登录', exact: true }).waitFor();
    checks.push('logout');
    assert.deepEqual(errors, [], 'browser runtime errors');
    checks.push('no browser runtime errors');
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify({ checks, errors, synthetic: true }, null, 2));
    console.log(`PASS: ${checks.length} browser smoke checks`);
  } finally {
    if (browser) await browser.close();
    server.kill();
    fs.closeSync(log);
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

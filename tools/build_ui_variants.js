/* ============================================================
   生成 3 个 PestGuard 前端界面变体。
   - 逻辑核心（API / 鉴权 / 票据 / 轮询 / 渲染）只写一份，保证都能真跑
   - 每个变体只提供自己的样式与文案微调
   用法：node tools/build_ui_variants.js
   ============================================================ */
const fs = require('fs');
const path = require('path');

const OUT_DIR = path.join(__dirname, '..', 'backend', 'static');

/* ── 三套主题变量 ─────────────────────────────────────────────── */
const THEMES = {
  v2: {
    name: '深色科技风',
    // 深色 + 数据感，偏"监控台/工作台"
    vars: `
  --bg:#0a1410; --bg-2:#0e1c17; --panel:#122520; --panel-2:#16302a;
  --line:#1f4038; --line-2:#2a5449;
  --fg:#eaf6ef; --fg-2:#a8c6b8; --fg-3:#6f8f83;
  --brand:#4ade9b; --brand-2:#8ef0bd; --brand-ink:#06231a;
  --accent:#3ba9ff; --warn:#f0b429; --danger:#ff6b5e;
  --shadow-1:0 1px 2px rgba(0,0,0,.4);
  --shadow-2:0 24px 60px -24px rgba(0,0,0,.75);
  --radius:10px; --radius-sm:8px; --radius-lg:14px;
  --ring:0 0 0 3px rgba(74,222,155,.35);
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  --mono:"SFMono-Regular",Consolas,Menlo,monospace;`,
    base: `
body{background:var(--bg);color:var(--fg)}
.wrap{max-width:1320px}
/* 顶部用一条品牌色进度带代替装饰 */
header.top{background:rgba(10,20,16,.9);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:40}
header.top::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:1px;
  background:linear-gradient(90deg,transparent,var(--brand),transparent);opacity:.5}
.top-in{height:56px}
.brand{color:var(--fg)}
.brand small{color:var(--fg-3)}
.brand .mark{background:linear-gradient(135deg,var(--brand),#1c8f63);border-radius:8px}
.card{background:var(--panel);border:1px solid var(--line);box-shadow:none}
.card h2{color:var(--fg)}
.card h2 .n{background:var(--panel-2);color:var(--brand);border:1px solid var(--line-2);border-radius:6px}
.sub,.note,.hint,.stat span,.item .tm,.ref .src{color:var(--fg-3)}
.hero{padding:34px 0 22px;text-align:left}
.hero h1{font-size:clamp(24px,3.4vw,38px);color:var(--fg)}
.hero h1 em{background:linear-gradient(96deg,var(--brand),var(--accent));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.hero p{color:var(--fg-2);margin-left:0;max-width:720px}
.pill{background:var(--panel);border-color:var(--line);color:var(--fg-2);border-radius:8px}
.pill .dot{background:var(--brand)}
.pill .dot.off{background:var(--warn)}
.btn{background:var(--panel-2);color:var(--fg);border:1px solid var(--line-2);border-radius:8px}
.btn:hover{background:#1b3b33;box-shadow:none}
.btn-primary{background:var(--brand);color:var(--brand-ink);border-color:var(--brand)}
.btn-primary:hover{background:var(--brand-2)}
.btn-lime{background:transparent;color:var(--brand);border-color:var(--brand)}
.btn-lime:hover{background:rgba(74,222,155,.12)}
.btn-danger{color:var(--danger);border-color:rgba(255,107,94,.4)}
.btn-danger:hover{background:rgba(255,107,94,.12)}
.who{background:var(--panel-2);border-color:var(--line);color:var(--fg-2);border-radius:8px}
.field input,.field select,.field textarea,.chat-in textarea{
  background:var(--bg-2);border-color:var(--line);color:var(--fg)}
.field input:focus,.field select:focus,.field textarea:focus,
.chat-in textarea:focus{border-color:var(--brand);background:var(--panel)}
.field label{color:var(--fg-2)}
.tabs{background:var(--bg-2);border:1px solid var(--line)}
.tabs button{color:var(--fg-3)}
.tabs button[aria-selected=true]{background:var(--panel-2);color:var(--brand);box-shadow:none}
.drop{background:var(--bg-2);border-color:var(--line-2);border-radius:8px}
.drop:hover,.drop.over{border-color:var(--brand);background:rgba(74,222,155,.08)}
.stage{background:#05100c;border:1px solid var(--line);border-radius:8px}
.chip{background:var(--panel-2);border-color:var(--line-2);color:var(--fg)}
.chip .c{color:var(--fg-3)}
.chip.up{border-color:var(--brand);color:var(--brand);background:rgba(74,222,155,.1)}
.chip.down{border-color:rgba(240,180,41,.5);color:var(--warn);background:rgba(240,180,41,.1)}
.bar .v{color:var(--brand);font-family:var(--mono)}
.bar .track{background:var(--bg-2)}
.bar .track i{background:linear-gradient(90deg,#1c8f63,var(--brand))}
.advice{border-top-color:var(--line)}
.advice .body h4{color:var(--brand-2)}
.advice .body{color:var(--fg-2)}
.advice .body h4{color:var(--fg)}
.cite{background:rgba(74,222,155,.14);color:var(--brand);border-color:rgba(74,222,155,.4);font-family:var(--mono)}
.cite:hover{background:rgba(74,222,155,.26)}
.refs{border-top-color:var(--line)}
.refs summary{color:var(--fg-2)}
.ref{border-bottom-color:var(--line)}
.ref p{color:var(--fg-2)}
.badge{background:var(--panel-2);color:var(--fg-2);border:1px solid var(--line-2)}
.badge-completed{background:rgba(74,222,155,.14);color:var(--brand);border-color:rgba(74,222,155,.4)}
.badge-failed{background:rgba(255,107,94,.14);color:var(--danger);border-color:rgba(255,107,94,.4)}
.badge-queued,.badge-processing{background:rgba(59,169,255,.14);color:var(--accent);border-color:rgba(59,169,255,.4)}
.seg{background:var(--bg-2);border:1px solid var(--line)}
.seg button{color:var(--fg-3)}
.seg button[aria-pressed=true]{background:var(--panel-2);color:var(--brand);box-shadow:none}
.item{border-radius:10px}
.item .thumb{background:var(--bg-2);border-radius:8px}
.stat{background:var(--panel);border:1px solid var(--line)}
.stat b{color:var(--brand);font-family:var(--mono)}
.bub.u{background:var(--brand);color:var(--brand-ink)}
.bub.a{background:var(--panel-2);color:var(--fg)}
.chat{border-top-color:var(--line)}
.empty{color:var(--fg-3)}
.modal-in{background:var(--panel);border:1px solid var(--line-2)}
.toast{background:var(--panel-2);border:1px solid var(--line-2);color:var(--fg)}
.toast.ok{background:#12513a;border-color:var(--brand)}
.toast.err{background:#5a2019;border-color:var(--danger)}
footer{color:var(--fg-3)}
footer code{background:var(--panel-2);border-color:var(--line)}
.msg.err{background:rgba(255,107,94,.14);color:var(--danger)}
.msg.ok{background:rgba(74,222,155,.14);color:var(--brand)}
.bg{display:none}`,
  },

  v3: {
    name: '移动优先·大字版',
    // 大按钮、大字号、高对比，面向"农户在地里举着手机"
    vars: `
  --bg:#ffffff; --bg-2:#f5f7f4; --panel:#ffffff; --panel-2:#eef3ec;
  --line:#dde5da; --line-2:#c4d2c0;
  --fg:#12210f; --fg-2:#41553c; --fg-3:#7a8c74;
  --brand:#1f7a3f; --brand-2:#2e9c52; --brand-ink:#ffffff;
  --accent:#a35b00; --warn:#a35b00; --danger:#b3261e;
  --shadow-1:0 1px 2px rgba(18,33,15,.06);
  --shadow-2:0 20px 50px -20px rgba(18,33,15,.3);
  --radius:18px; --radius-sm:14px; --radius-lg:26px;
  --ring:0 0 0 4px rgba(31,122,63,.25);
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  --mono:ui-monospace,Consolas,monospace;`,
    base: `
body{background:var(--bg);color:var(--fg);font-size:17px;line-height:1.75}
.wrap{max-width:760px;padding:0 18px}
header.top{background:#fff;border-bottom:2px solid var(--line)}
.top-in{height:74px}
.brand{font-size:20px}
.brand small{font-size:12px;color:var(--fg-3)}
.brand .mark{width:40px;height:40px;border-radius:12px;background:var(--brand)}
.hero{padding:26px 0 18px;text-align:left}
.hero h1{font-size:clamp(28px,7vw,40px);line-height:1.25;letter-spacing:-.5px}
.hero h1 em{color:var(--brand);-webkit-text-fill-color:currentColor;background:none}
.hero p{font-size:17px;color:var(--fg-2);margin:12px 0 0;max-width:none}
.pill{font-size:14px;padding:8px 16px;background:var(--panel-2);border-color:var(--line-2);
  color:var(--fg-2);border-radius:999px}
.pill .dot{width:9px;height:9px}
.btn{min-height:56px;padding:14px 24px;font-size:17px;font-weight:700;border-radius:16px;
  background:var(--panel-2);border:2px solid var(--line-2);color:var(--fg)}
.btn-primary{background:var(--brand);color:#fff;border-color:var(--brand)}
.btn-primary:hover{background:var(--brand-2)}
.btn-lime{background:var(--brand);color:#fff;border-color:var(--brand);font-size:18px}
.btn-sm{min-height:46px;padding:10px 18px;font-size:15px}
.btn-danger{color:var(--danger);border-color:#e8b4b0}
/* 单列，卡片间距更大 */
.grid.two{grid-template-columns:1fr !important;gap:18px}
.card{border:2px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow-1)}
.card-pad{padding:20px}
.card h2{font-size:19px}
.card h2 .n{width:28px;height:28px;font-size:14px;border-radius:10px;
  background:var(--brand);color:#fff}
.sub{font-size:14.5px;color:var(--fg-2)}
.field label{font-size:15.5px;font-weight:700}
.field input,.field select,.field textarea{font-size:17px;padding:15px 16px;
  border:2px solid var(--line-2);border-radius:14px;background:#fff}
.drop{padding:34px 20px;border:3px dashed var(--line-2);border-radius:18px;background:var(--bg-2)}
.drop .ic{font-size:40px}
.drop b{font-size:19px;margin-top:12px}
.drop small{font-size:14.5px;color:var(--fg-2)}
.row{gap:14px}
.row .btn{flex:1 1 auto}
.stage{min-height:220px;border-radius:16px;background:#eef3ec}
.stage .ph{color:var(--fg-3);font-size:15px}
.chips{gap:10px}
.chip{font-size:15px;padding:8px 14px;border-radius:999px;background:var(--panel-2);
  border:2px solid var(--line)}
.chip.up{background:#e4f4e8;border-color:var(--brand);color:var(--brand)}
.chip .c{font-size:13.5px}
.bar{font-size:15.5px}
.bar .track{height:10px;border-radius:999px}
.bar .v{font-size:14px;font-weight:700;color:var(--brand)}
.advice{border-top:2px solid var(--line);padding-top:18px}
.advice h3{font-size:18px}
.advice .body{font-size:17px;line-height:1.85}
.advice .body h4{font-size:17.5px;margin:20px 0 8px}
.cite{min-width:22px;height:22px;font-size:13px;border-radius:7px;background:#e4f4e8;
  border:1.5px solid var(--brand);color:var(--brand)}
.refs summary{font-size:16px;padding:8px 0}
.ref{font-size:15.5px;padding:14px 0}
.ref .src{font-size:13.5px}
.badge{font-size:13.5px;padding:5px 12px}
.stats{grid-template-columns:repeat(2,1fr);gap:14px}
.stat{padding:18px;border:2px solid var(--line);border-radius:var(--radius)}
.stat b{font-size:30px;color:var(--brand)}
.stat span{font-size:14.5px;color:var(--fg-2)}
.list{grid-template-columns:1fr !important}
.item{padding:16px;border:2px solid var(--line);border-radius:18px}
.item .thumb{width:110px;height:110px;border-radius:14px}
.item .nm{font-size:16.5px}
.item .tm{font-size:13.5px}
.item .cs .chip{font-size:14px;padding:5px 11px}
.seg{background:var(--panel-2);border:2px solid var(--line);border-radius:14px;padding:4px}
.seg button{padding:10px 18px;font-size:15.5px;border-radius:11px}
.chat-in textarea{font-size:17px;border:2px solid var(--line-2);border-radius:14px;min-height:56px}
.bub{font-size:16.5px;padding:13px 16px;border-radius:16px;max-width:94%}
.chat-log{max-height:340px}
.toast{font-size:16px;padding:15px 18px;border-radius:14px}
.note{font-size:14.5px;color:var(--fg-2);line-height:1.7}
.empty{font-size:16px}
footer{font-size:14px;color:var(--fg-3)}
/* 移动端把操作区吸底，方便单手 */
@media(max-width:640px){
  .hero{padding:18px 0 12px}
  .hero h1{font-size:30px}
  .stats{gap:10px}
  .stat b{font-size:26px}
}`,
  },

  v4: {
    name: '编辑风·杂志版',
    // 大留白、衬线标题、高对比，偏"作品集/展示页"
    vars: `
  --bg:#f7f5ef; --bg-2:#efece2; --panel:#fffdf8; --panel-2:#efece2;
  --line:#e0dbcc; --line-2:#cfc7b2;
  --fg:#1b1a17; --fg-2:#57534a; --fg-3:#8d8778;
  --brand:#9c2d16; --brand-2:#c0432a; --brand-ink:#fffdf8;
  --accent:#1f4d3d; --warn:#8a5a00; --danger:#9c2d16;
  --shadow-1:0 1px 0 rgba(27,26,23,.06);
  --shadow-2:0 30px 60px -30px rgba(27,26,23,.4);
  --radius:4px; --radius-sm:3px; --radius-lg:6px;
  --ring:0 0 0 3px rgba(156,45,22,.25);
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  --serif:Georgia,"Songti SC","Source Han Serif SC","Noto Serif CJK SC",serif;
  --mono:"SFMono-Regular",Consolas,Menlo,monospace;`,
    base: `
body{background:var(--bg);color:var(--fg);line-height:1.8}
.wrap{max-width:1080px}
header.top{background:var(--bg);border-bottom:1px solid var(--fg);position:sticky;top:0;z-index:40}
.top-in{height:64px}
.brand{font-family:var(--serif);font-size:21px;letter-spacing:-.3px}
.brand small{font-family:var(--font);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--fg-3)}
.brand .mark{border-radius:2px;background:var(--brand)}
/* 报头式 Hero */
.hero{padding:56px 0 40px;text-align:left;border-bottom:1px solid var(--line)}
.hero .pill{display:none}
.hero h1{font-family:var(--serif);font-size:clamp(32px,5.4vw,62px);line-height:1.06;
  letter-spacing:-1.5px;font-weight:400}
.hero h1 em{color:var(--brand);-webkit-text-fill-color:currentColor;background:none;font-style:italic}
.hero p{font-size:18px;color:var(--fg-2);margin:20px 0 0;max-width:660px;line-height:1.75}
.kicker{font-family:var(--font);font-size:11.5px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--brand);font-weight:700;margin-bottom:14px;display:block}
.card{background:transparent;border:none;border-top:2px solid var(--fg);border-radius:0;
  box-shadow:none;padding-left:0;padding-right:0}
.card-pad{padding:26px 0 0}
.card h2{font-family:var(--serif);font-size:24px;font-weight:400;letter-spacing:-.3px}
.card h2 .n{display:none}
.sub{font-size:14px;color:var(--fg-3)}
.grid{gap:34px}
.grid.two{gap:34px}
@media(min-width:960px){.grid.two{grid-template-columns:minmax(0,320px) minmax(0,1fr)}}
.btn{border-radius:2px;border:1px solid var(--fg);background:transparent;color:var(--fg);
  padding:12px 20px;font-size:14px;letter-spacing:.02em;font-weight:600}
.btn:hover{background:var(--fg);color:var(--bg);box-shadow:none}
.btn-primary{background:var(--brand);border-color:var(--brand);color:var(--brand-ink)}
.btn-primary:hover{background:var(--brand-2);border-color:var(--brand-2);color:#fff}
.btn-lime{background:var(--fg);border-color:var(--fg);color:var(--bg)}
.btn-lime:hover{background:var(--brand);border-color:var(--brand);color:#fff}
.btn-danger{color:var(--brand);border-color:var(--brand)}
.btn-danger:hover{background:var(--brand);color:#fff}
.who{border-radius:2px;border-color:var(--line-2);background:var(--panel)}
.field label{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--fg-3);font-weight:700}
.field input,.field select,.field textarea{border-radius:2px;border:1px solid var(--line-2);
  background:var(--panel);padding:13px 14px;font-size:15.5px}
.field input:focus,.field select:focus,.field textarea:focus{border-color:var(--brand)}
.tabs{background:transparent;padding:0;gap:0;border-bottom:1px solid var(--line);border-radius:0}
.tabs button{border-radius:0;padding:12px 18px;font-size:15px}
.tabs button[aria-selected=true]{background:transparent;box-shadow:none;color:var(--fg);
  border-bottom:2px solid var(--brand);margin-bottom:-1px}
.drop{border-radius:2px;border:1px dashed var(--line-2);background:var(--bg-2);padding:30px 18px}
.drop.over{border-color:var(--brand);background:#f3ece4}
.stage{background:var(--fg);border-radius:2px;min-height:220px}
.chip{border-radius:2px;border:1px solid var(--line-2);background:var(--panel);
  font-size:13px;padding:4px 10px;letter-spacing:.01em}
.chip.up{border-color:var(--brand);color:var(--brand);background:#f7ece7}
.chip.down{border-color:var(--warn);color:var(--warn);background:#f7f2e4}
.bars{gap:12px}
.bar .t{font-family:var(--serif);font-size:16px}
.bar .track{height:2px;background:var(--line-2);border-radius:0}
.bar .track i{background:var(--brand);border-radius:0}
.bar .v{font-family:var(--mono);color:var(--brand);font-size:13px}
.advice{border-top:1px solid var(--line);margin-top:24px;padding-top:20px}
.advice h3{font-family:var(--serif);font-size:19px;font-weight:400}
.advice h3 .badge{font-family:var(--font)}
.advice .body{font-size:16.5px;line-height:1.9;color:var(--fg)}
.advice .body h4{font-family:var(--serif);font-size:17px;font-weight:400;
  letter-spacing:.01em;margin:22px 0 6px;color:var(--brand)}
.cite{border-radius:2px;background:#f7ece7;border:1px solid var(--brand);color:var(--brand);
  min-width:18px;height:18px;font-size:11px}
.refs{border-top:1px solid var(--line);margin-top:16px}
.refs summary{font-size:13.5px;letter-spacing:.02em;color:var(--fg-2)}
.ref{font-size:14px;padding:12px 0;border-bottom:1px solid var(--line)}
.ref b{font-family:var(--serif);font-weight:400;font-size:15px}
.badge{border-radius:2px;border:1px solid var(--line-2);background:var(--panel);
  font-size:11.5px;letter-spacing:.03em}
.badge-completed{border-color:var(--accent);color:var(--accent);background:#eaf0ed}
.badge-failed{border-color:var(--brand);color:var(--brand);background:#f7ece7}
.stats{gap:0;margin-top:0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.stat{background:transparent;border:none;border-right:1px solid var(--line);border-radius:0;padding:22px 18px}
.stat:last-child{border-right:none}
.stat b{font-family:var(--serif);font-size:34px;font-weight:400;color:var(--fg);letter-spacing:-1px}
.stat span{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--fg-3)}
.list{gap:0 !important;grid-template-columns:1fr !important}
.item{border:none;border-bottom:1px solid var(--line);border-radius:0;padding:22px 0}
.item .thumb{width:104px;height:104px;border-radius:2px}
.item .nm{font-family:var(--serif);font-size:19px;font-weight:400}
.item .tm{font-size:12.5px;letter-spacing:.03em}
.seg{background:transparent;padding:0;border:1px solid var(--line);border-radius:2px}
.seg button{border-radius:0;font-size:13px;letter-spacing:.04em}
.seg button[aria-pressed=true]{background:var(--fg);color:var(--bg);box-shadow:none}
.chat{border-top:1px solid var(--line)}
.chat-in textarea{border-radius:2px;border:1px solid var(--line-2);background:var(--panel)}
.bub{border-radius:2px;font-size:15px}
.bub.u{background:var(--fg);color:var(--bg)}
.bub.a{background:var(--panel-2);border:1px solid var(--line)}
.toast{border-radius:2px;background:var(--fg);color:var(--bg)}
.toast.ok{background:var(--accent);color:#fff}
.toast.err{background:var(--brand);color:#fff}
footer{border-top:1px solid var(--line);padding-top:22px;margin-top:56px;font-size:12.5px;
  letter-spacing:.03em;color:var(--fg-3)}
.empty{color:var(--fg-3);font-family:var(--serif);font-size:17px}
.bg i{opacity:.25;filter:blur(110px)}
.bg i:nth-child(1){background:rgba(156,45,22,.18)}
.bg i:nth-child(2){background:rgba(31,77,61,.16)}
.bg i:nth-child(3){background:rgba(207,199,178,.5)}`,
  },
};

/* ── 共享逻辑（与 v1 完全同源，只改主题挂载点） ─────────────────── */
const SHARED_JS = fs.readFileSync(path.join(OUT_DIR, 'v1.html'), 'utf8')
  .match(/<script>\n"use strict";([\s\S]*?)<\/script>/)[1];

/* 两个双列变体共用的修版补丁：
   左栏（上传卡）比右栏（结果+建议）短很多，滚到建议区时左边会空出一大片。
   把左栏在桌面宽度下粘住，滚动时它一直在视野里，右侧长文可以顺畅读。 */
const STICKY_LEFT = `
/* 双列时左栏内容短、右栏（结果+建议）很长 —— 滚下去左边会空一大片。
   桌面宽度下让左栏粘住，视觉重心不散。 */
@media(min-width:960px){
  .grid.two > .card:first-child{
    position:sticky; top:76px;
    max-height:calc(100vh - 96px); overflow-y:auto;
  }
}
@media(prefers-reduced-motion:reduce){ .grid.two > .card:first-child{position:static} }`;

/* ── 页面骨架 ─────────────────────────────────────────────────── */
function build(key) {
  const th = THEMES[key];
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#12291f">
<meta name="description" content="PestGuard · 农作物害虫智能识别与植保决策平台。">
<title>PestGuard · 害虫智能识别与植保决策</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%23173f34'/%3E%3Cpath d='M24 7c0 9-6 14-13 14 0-8 5-13 13-14z' fill='%23d9ed7a'/%3E%3C/svg%3E">
<!-- 变体：${th.name}（由 tools/build_ui_variants.js 生成，请勿直接手改） -->
<style>
:root{${th.vars}
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
img,video{max-width:100%;display:block}
button,input,select,textarea{font:inherit;color:inherit}
button{cursor:pointer;border:none;background:none}
a{color:inherit;text-underline-offset:2px}
:focus-visible{outline:none;box-shadow:var(--ring);border-radius:6px}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
.skip{position:absolute;left:-9999px;top:0;z-index:100;background:var(--brand);color:#fff;padding:10px 16px}
.skip:focus{left:0}
.bg{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
.bg i{position:absolute;border-radius:50%;filter:blur(80px);opacity:.5}
.bg i:nth-child(1){width:520px;height:520px;background:rgba(217,237,122,.55);top:-180px;left:-140px}
.bg i:nth-child(2){width:460px;height:460px;background:rgba(47,107,86,.18);bottom:-200px;right:-120px}
.bg i:nth-child(3){width:380px;height:380px;background:rgba(47,92,143,.12);top:44%;right:34%}
.wrap{position:relative;z-index:1;max-width:1200px;margin:0 auto;padding:0 20px}
@media(max-width:640px){.wrap{padding:0 14px}}
.top-in{display:flex;align-items:center;gap:14px}
.brand{display:flex;align-items:center;gap:10px;font-weight:750;letter-spacing:-.2px;font-size:17px}
.brand .mark{width:32px;height:32px;display:grid;place-items:center;flex:none}
.brand small{display:block;font-size:11px;font-weight:500}
.spacer{flex:1}
.who{display:flex;align-items:center;gap:8px;font-size:13px;padding:5px 6px 5px 12px;
  border:1px solid var(--line);border-radius:999px}
.who b{font-weight:650;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:10px 18px;
  font-size:14px;font-weight:600;transition:background .14s,color .14s,transform .14s;min-height:40px}
.btn:active{transform:translateY(1px)}
.btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
.btn-sm{padding:7px 13px;font-size:13px;min-height:34px}
.btn-ghost{background:transparent;border-color:transparent}
.pill{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:600;
  padding:5px 13px;border:1px solid var(--line);border-radius:999px;margin-bottom:16px}
.pill .dot{width:6px;height:6px;border-radius:50%;background:var(--brand);flex:none}
.grid{display:grid;gap:20px;align-items:start}
@media(min-width:960px){.grid.two{grid-template-columns:minmax(0,1.05fr) minmax(0,1fr)}}
.card-pad{padding:22px}
@media(max-width:640px){.card-pad{padding:16px}}
.card h2{font-size:16px;font-weight:700;display:flex;align-items:center;gap:8px}
.card h2 .n{width:22px;height:22px;font-size:12px;display:grid;place-items:center;flex:none;font-weight:700}
.sub{font-size:13px;margin-top:4px}
.auth{max-width:430px;margin:36px auto 0}
.tabs{display:flex;gap:4px;padding:4px;margin-bottom:20px}
.tabs button{flex:1;padding:9px;font-size:14px;font-weight:600}
.field{margin-bottom:14px}
.field label{display:block;font-size:13px;font-weight:600;margin-bottom:6px}
.field input,.field select,.field textarea{width:100%;padding:11px 13px;border:1px solid var(--line-2);
  background:var(--bg-2);transition:border-color .14s}
.field .hint{font-size:12px;color:var(--fg-3);margin-top:5px}
.msg{font-size:13px;padding:10px 13px;margin-bottom:14px;display:none}
.msg.show{display:block}
.drop{text-align:center;transition:border-color .16s,background .16s;cursor:pointer}
.drop .ic{font-size:26px}
.drop b{display:block;margin-top:8px;font-size:15px}
.drop small{font-size:12.5px}
.row{display:flex;gap:9px;flex-wrap:wrap;margin-top:14px}
.progress{height:5px;background:var(--line);overflow:hidden;margin-top:14px;display:none}
.progress.show{display:block}
.progress i{display:block;height:100%;width:38%;background:var(--brand);animation:slide 1.15s ease-in-out infinite}
@keyframes slide{0%{margin-left:-40%}100%{margin-left:100%}}
.note{font-size:12px;margin-top:12px;line-height:1.6}
.stage{overflow:hidden;position:relative;display:grid;place-items:center}
.stage img,.stage video{width:100%;height:auto;display:block}
.stage .ph{text-align:center;padding:30px 18px}
.stage .ph .ic{font-size:30px;display:block;margin-bottom:8px;opacity:.55}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}
.chip{display:inline-flex;align-items:center;gap:6px;font-weight:600;border:1px solid var(--line)}
.bars{margin-top:16px;display:grid;gap:9px}
.bar{display:grid;grid-template-columns:1fr auto;gap:4px 10px;align-items:center;font-size:13px}
.bar .t{font-weight:600;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.bar .track{grid-column:1/-1;height:6px;overflow:hidden}
.bar .track i{display:block;height:100%}
.advice{margin-top:18px;padding-top:16px}
.advice h3{font-size:14px;font-weight:700;display:flex;align-items:center;gap:7px;margin-bottom:9px}
.advice .body p{margin:0 0 10px}
.advice .body p:last-child{margin-bottom:0}
.advice .body h4{font-size:14px;font-weight:700;margin:16px 0 7px}
.advice .body h4:first-child{margin-top:0}
.cite{display:inline-grid;place-items:center;min-width:17px;height:17px;padding:0 4px;margin:0 1px;
  font-size:10.5px;font-weight:700;vertical-align:super;cursor:pointer}
.refs{margin-top:12px;padding-top:10px}
.refs summary{font-weight:600;cursor:pointer;list-style:none}
.refs summary::-webkit-details-marker{display:none}
.refs summary::before{content:"▸ ";color:var(--fg-3)}
.refs[open] summary::before{content:"▾ "}
.ref{padding:11px 0;border-bottom:1px dashed var(--line)}
.ref:last-child{border-bottom:none}
.ref b{font-weight:650}
.ref .src{font-size:12px}
.ref p{margin-top:4px;line-height:1.7}
.empty{text-align:center;padding:38px 18px}
.empty .ic{font-size:30px;display:block;margin-bottom:9px;opacity:.5}
.hist{margin-top:30px}
.hist-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.hist-head h2{font-size:16px;font-weight:700}
.seg{display:flex;gap:3px;padding:3px}
.seg button{padding:6px 13px;font-size:13px;font-weight:600}
.list{display:grid;gap:14px}
@media(min-width:820px){.list{grid-template-columns:repeat(2,minmax(0,1fr))}}
.item{display:flex;gap:14px;padding:14px}
.item .thumb{width:96px;height:96px;flex:none;overflow:hidden;position:relative}
.item .thumb img{width:100%;height:100%;object-fit:cover}
.item .thumb .v{width:100%;height:100%;display:grid;place-items:center;font-size:24px}
.item .meta{min-width:0;flex:1;display:flex;flex-direction:column}
.item .nm{font-size:14px;font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item .tm{font-size:12px;margin-top:2px}
.item .cs{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}
.item .cs .chip{padding:3px 9px;font-size:12px}
.item .acts{margin-top:auto;padding-top:9px;display:flex;gap:7px;flex-wrap:wrap}
.badge{font-size:11.5px;font-weight:700;padding:3px 9px;display:inline-block}
.badge + .badge,.chip + .badge,.badge + .chip{margin-left:6px}
.advice h3 .badge{font-weight:600}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:26px}
@media(max-width:640px){.stats{grid-template-columns:repeat(2,1fr)}}
.stat b{display:block;font-size:24px;font-weight:800;letter-spacing:-.6px;font-variant-numeric:tabular-nums}
.stat span{font-size:12.5px}
.modal{position:fixed;inset:0;z-index:60;background:rgba(13,31,25,.72);display:grid;
  place-items:center;padding:18px}
.modal[hidden]{display:none}
.modal-in{max-width:min(92vw,880px);max-height:92vh;overflow:auto;position:relative;box-shadow:var(--shadow-2)}
.modal-in img{width:100%;height:auto}
.modal-close{position:absolute;top:10px;right:10px;width:34px;height:34px;border-radius:50%;
  background:rgba(13,31,25,.66);color:#fff;display:grid;place-items:center;font-size:16px}
.chat{margin-top:16px;padding-top:14px;border-top:1px solid var(--line)}
.chat-log{max-height:260px;overflow-y:auto;display:grid;gap:9px;margin:10px 0}
.bub{max-width:88%;padding:9px 13px;font-size:13.5px;line-height:1.7;white-space:pre-wrap}
.chat-in{display:flex;gap:8px}
.chat-in textarea{flex:1;resize:none;min-height:42px;max-height:120px;padding:10px 13px}
.toasts{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:80;display:grid;
  gap:8px;width:min(92vw,440px)}
.toast{padding:11px 15px;font-size:13.5px;display:flex;gap:10px;align-items:flex-start;animation:up .22s ease}
@keyframes up{from{opacity:0;transform:translateY(10px)}}
.toast button{opacity:.7;font-size:15px;line-height:1;flex:none}
footer{margin:50px 0 30px;text-align:center;font-size:12.5px;line-height:1.9}
footer code{padding:2px 6px;border:1px solid var(--line)}
${th.base}
</style>
</head>
<body>
<div class="bg" aria-hidden="true"><i></i><i></i><i></i></div>
<a class="skip" href="#main">跳到主内容</a>

<header class="top">
  <div class="wrap top-in">
    <div class="brand">
      <span class="mark" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M20 4c0 8.5-4.5 13-11 13H5c0-7.5 4.8-12.6 11-13 2.6-.2 4 .8 4 0Z" fill="#d9ed7a"/>
          <path d="M4 21c1.5-5 4.5-9 9-12" stroke="#f0f8cf" stroke-width="1.6" stroke-linecap="round"/>
        </svg>
      </span>
      <span>PestGuard<small>害虫识别与植保决策</small></span>
    </div>
    <span class="spacer"></span>
    <div id="nav"></div>
  </div>
</header>

<main id="main" class="wrap">
  <section class="hero">
    <span class="pill"><span class="dot" id="sysDot"></span><span id="sysText">正在检查服务状态…</span></span>
    <h1>拍一张叶片照片，<em>认出虫、说清怎么治</em></h1>
    <p>视觉模型定位虫体并判定虫种，结合作物上下文与植保知识库生成防治建议，每条结论都可追溯到出处。</p>
  </section>

  <section class="stats" id="stats" hidden>
    <div class="stat"><b id="sTotal">—</b><span>累计检测</span></div>
    <div class="stat"><b id="sObj">—</b><span>识别虫体</span></div>
    <div class="stat"><b id="sClass">—</b><span>虫种类别</span></div>
    <div class="stat"><b id="sOk">—</b><span>成功 / 总数</span></div>
  </section>

  <div id="app"></div>

  <footer>
    <div>PestGuard · 农作物害虫智能识别与植保决策平台</div>
    <div>识别结果与防治建议由视觉模型与植保知识库联合生成，请结合田间实际复核。</div>
    <div style="margin-top:6px"><code>/docs</code> 查看接口文档</div>
  </footer>
</main>

<div class="toasts" id="toasts" role="status" aria-live="polite"></div>

<div class="modal" id="modal" hidden role="dialog" aria-modal="true" aria-label="查看大图">
  <div class="modal-in">
    <button class="modal-close" id="modalClose" aria-label="关闭大图">✕</button>
    <img id="modalImg" alt="">
  </div>
</div>

<script>
"use strict";${SHARED_JS}</script>
</body>
</html>
`;
}

for (const k of Object.keys(THEMES)) {
  const file = path.join(OUT_DIR, k + '.html');
  fs.writeFileSync(file, build(k), 'utf8');
  console.log('生成', k + '.html', (fs.statSync(file).size / 1024).toFixed(1) + ' KB', '·', THEMES[k].name);
}

// ===== 信息弹窗（联系我们 / 模型说明 / 源码与部署）=====
// 页脚的「模型说明」「源码与部署」与 CTA 的「联系我们」原先是 href="#" 的空链接，
// 点击只会跳回页面顶部，等于点了没有任何展示。这里统一改成弹窗。
// 内容全部取自项目真实产物（模型指标来自 model_weights/training_metrics.json），不写虚数。
const CONTACT_EMAIL = '1826244602@qq.com';

const INFO_PANELS = {
  contact: {
    title: '联系我们',
    sub: '禾察 为参赛演示作品。技术方案、数据合作与部署咨询，欢迎随时来信。',
    rows: [
      ['联系邮箱', '<span class="im-mail">' + CONTACT_EMAIL + '</span>'],
      ['项目性质', '2026 华北五省大学生计算机应用大赛 · 参赛作品'],
      ['交流范围', '技术方案 · 数据合作 · 部署咨询'],
    ],
    note: '我们通常在 1 个工作日内回复。如需现场演示或测试账号，也欢迎邮件说明。',
    actions: [{ text: '📋 复制邮箱', copy: true }, { text: '关闭', ghost: true }],
  },
  model: {
    title: '模型说明',
    sub: 'YOLOv8-GS 轻量化目标检测网络，针对田间细粒度虫体识别优化。',
    rows: [
      ['网络结构', 'YOLOv8-GS（改进版）'],
      ['识别类别', '46 类农作物害虫'],
      ['mAP@0.5', '<span class="im-hl">76.92%</span>'],
      ['mAP@0.5:0.95', '48.77%'],
      ['精确率 / 召回率', '75.13% / 69.83%'],
      ['参数量 / 权重体积', '2.62 M / 9.93 MB'],
      ['推理速度', '78.6 ms · 12.7 FPS（CPU 单图）'],
      ['训练轮次', '150 轮 · 最优第 88 轮'],
    ],
    note: '指标取自 2025-03-18 的最佳权重训练记录。模型按端侧部署优化，无 GPU 环境同样可实时推理。',
    actions: [{ text: '查看技术链路', scroll: 'pipe', ghost: true }, { text: '关闭', ghost: true }],
  },
  source: {
    title: '源码与部署',
    sub: '全栈自研，容器化一键部署。',
    rows: [
      ['后端', 'FastAPI + SQLAlchemy + Redis（Python 2209 行）'],
      ['前端', 'React 18 + TypeScript + Vite（665 行）'],
      ['视觉推理', 'Ultralytics YOLO · CPU / GPU 双模式'],
      ['大模型', 'DeepSeek + RAG 检索增强（知识库 69 条）'],
      ['部署方式', 'Docker Compose 一键启动 · Nginx 反向代理'],
      ['质量保障', '48 项自动化测试全部通过'],
    ],
    note: '按大赛要求，完整源码随作品提交包一并交付；部署脚本与使用说明见提交文档。',
    actions: [{ text: '关闭', ghost: true }],
  },
};

function openInfo(key) {
  const cfg = INFO_PANELS[key];
  if (!cfg) return;
  $('imTitle').textContent = cfg.title;
  const rows = '<dl class="im-kv">'
    + cfg.rows.map(r => '<dt>' + r[0] + '</dt><dd>' + r[1] + '</dd>').join('') + '</dl>';
  const acts = '<div class="im-actions">' + (cfg.actions || []).map(a => {
    const fn = a.copy
      ? 'copyEmail(this)'
      : (a.scroll
          ? "closeInfo();document.getElementById('" + a.scroll + "').scrollIntoView({behavior:'smooth'})"
          : 'closeInfo()');
    return '<button class="im-btn' + (a.ghost ? ' ghost' : '') + '" onclick="' + fn + '">' + a.text + '</button>';
  }).join('') + '</div>';
  $('imBody').innerHTML = (cfg.sub ? '<div class="im-sub">' + cfg.sub + '</div>' : '')
    + rows + (cfg.note ? '<div class="im-note">' + cfg.note + '</div>' : '') + acts;
  $('infoModal').style.display = 'flex';
}

function closeInfo() { $('infoModal').style.display = 'none'; }
function openContact() { location.assign('/contact'); }
function openModelInfo() { location.assign('/model'); }
function openSourceInfo() { location.assign('/deployment'); }

// 优先 Clipboard API；以 http://内网IP 访问时它不是安全上下文、API 根本不存在，
// 回退到 execCommand + 临时 textarea，保证任何访问方式下都能复制成功。
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (e) { /* 落到下面的回退 */ }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;left:-9999px;top:0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    ta.remove();
    return ok;
  } catch (e) { return false; }
}

// 反馈落在被点击的元素本身（页脚链接或弹窗按钮），文字临时变成结果，1.6 秒后还原
async function copyEmail(el) {
  const ok = await copyText(CONTACT_EMAIL);
  if (!el) return;
  if (!el.dataset.orig) el.dataset.orig = el.textContent;
  el.textContent = ok ? '✓ 已复制' : '复制失败';
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.textContent = el.dataset.orig; }, 1600);
}


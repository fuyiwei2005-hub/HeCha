function imgBroken(el) {
  const box = el.closest('.hthumb') || el.parentElement;
  if (!box || box.dataset.broken) { el.style.display = 'none'; return; }
  box.dataset.broken = '1';
  const isVideo = el.tagName === 'VIDEO';
  const tip = document.createElement('div');
  tip.className = 'vstate vfail';
  tip.innerHTML = isVideo
    ? '视频无法播放<br><span>格式不受浏览器支持，或文件已被清理</span>'
    : '🗑️ 结果图已被清理<br><span>重新上传即可生成</span>';
  box.replaceChild(tip, el);
}

// ===== 历史 =====
// 视频结果「完整度」摘要。以前只说「N 个目标」，用户看不出到底扫了多少帧、
// 有没有漏掉后半段——这里把抽帧覆盖情况摊开写清楚。
function videoSummary(it) {
  const m = it.video_meta || {};
  const events = it.predictions || [];
  const flat = events.flatMap(ev => ev.detections || []);
  const parts = [];
  parts.push(m.full_scan
    ? '逐帧全检 <b>' + (m.sampled_frames || 0) + '</b> 帧'
    : '每 1/' + (m.sample_stride || '?') + ' 帧抽样，共 <b>' + (m.sampled_frames || 0) + '</b> 帧');
  if (m.duration_ms) parts.push('时长 <b>' + (m.duration_ms / 1000).toFixed(1) + 's</b>');
  if (m.fps) parts.push('原片 <b>' + m.fps + '</b> fps');
  let warn = '';
  if (m.h264 === false) {
    warn = '<span class="warn">⚠ 未转成 H.264，浏览器可能无法播放</span>';
  } else if (m.truncated) {
    warn = '<span class="warn">⚠ 视频较长，已按 1/' + (m.sample_stride || '?') + ' 帧抽样</span>';
  }
  // 覆盖情况：检出帧数 / 采样帧数，以及首次、末次检出的时间点
  let cov = '';
  if (events.length) {
    const t0 = events[0].time_ms || 0;
    const t1 = events[events.length - 1].time_ms || 0;
    const pct = m.sampled_frames ? Math.round(events.length / m.sampled_frames * 100) : 0;
    cov = '<br>检出 <b>' + events.length + '</b> 帧' +
          (m.sampled_frames ? '（占' + (m.full_scan ? '全片' : '采样') + ' ' + pct + '%）' : '') +
          ' · 出现于 <b>' + fmtMs(t0) + ' – ' + fmtMs(t1) +
          '</b> · 累计目标 ' + flat.length + ' 次';
  } else {
    cov = '<br>全程未检出目标';
  }
  return '<div class="vsum">' + parts.join(' · ') + cov + (warn ? '<br>' + warn : '') + '</div>';
}

function fmtMs(ms) {
  const s = (ms || 0) / 1000;
  const m = Math.floor(s / 60);
  const r = (s - m * 60).toFixed(1);
  return (m > 0 ? m + ':' + (r < 10 ? '0' + r : r) : r + 's');
}

// 逐帧时间线：把「结果给的不全」变成可核对的清单
function videoTimeline(it) {
  const events = (it.predictions || []).filter(ev => (ev.detections || []).length);
  if (!events.length) return '';
  const rows = events.map(ev => {
    const ds = ev.detections || [];
    const best = Math.max(...ds.map(d => d.confidence || 0));
    const names = [...new Set(ds.map(d => d.class_cn || d.class))].join('、');
    return '<div class="tl-row"><span class="tl-t">' + fmtMs(ev.time_ms) + '</span>' +
           '<span class="tl-c">' + esc(names) + ' <em>×' + ds.length + '</em></span>' +
           '<span class="tl-q">' + Math.round(best * 100) + '%</span></div>';
  }).join('');
  return '<div class="tl"><div class="tl-head" onclick="this.parentElement.classList.toggle(\'open\')">' +
         '<span>🕒 逐帧时间线（' + events.length + ' 帧检出）</span><span>▸</span></div>' +
         '<div class="tl-body">' + rows + '</div></div>';
}

// 长文本块内部滚动后需要一个「下面还有内容」的提示：未滚到底时挂 .has-more
// 显示底部渐隐，触底立即撤掉，否则切面看起来像内容缺失。
function bindScrollHint(el) {
  if (!el) return;
  if (el.dataset.hint !== '1') {
    el.dataset.hint = '1';
    el.addEventListener('scroll', () => updateScrollHint(el), { passive: true });
  }
  updateScrollHint(el);   // 内容更新后重新判定（元素常驻，不能只绑一次）
}
function updateScrollHint(el) {
  el.classList.toggle('has-more', el.scrollHeight - el.scrollTop - el.clientHeight > 4);
}

async function loadHistory() {
  if (!$('historyBox')) return;
  let rows = await api('/detections?limit=50');
  if (PAGE_NAME === 'video') rows = rows.filter(r => r.media_type === 'video');
  // 先把这批记录的短时票据换好，下面模板里就能同步取用
  await warmResultTickets(rows).catch(() => {});
  $('emptyTip').style.display = rows.length ? 'none' : 'block';
  $('historyBox').innerHTML = rows.map(it => {
    const d = new Date(it.created_at).toLocaleString('zh-CN');
    const isVideo = it.media_type === 'video';
    let thumb = '';
    let badge = it.status;

    // ── 视频：状态与播放分离，处理中显示进度提示，完成后给明确播放按钮 ──
    if (isVideo) {
      const done = it.status === 'completed' && it.result_url;
      if (done) {
        const vurl = resultUrl(it, it.result_url);
        thumb = vurl
          ? `<div class="vwrap" data-src="${esc(vurl)}">
            <div class="vposter"><span class="vplay">▶</span><span class="vtext">点击播放识别结果</span></div>
          </div>`
          : `<div class="vstate vbusy"><b>结果已就绪</b><span>刷新页面后即可播放</span></div>`;
      } else if (it.status === 'failed') {
        thumb = `<div class="vstate vfail">⚠️ 处理失败<br><span>${esc(it.error || '未知错误')}</span></div>`;
      } else {
        // queued / processing：给出可感知的进度，而不是一行冷冰冰的 processing
        const label = it.status === 'queued' ? '排队中…' : '正在逐帧识别…';
        thumb = `<div class="vstate vbusy"><div class="spin"></div><b>${label}</b>
            <span>约需 5–20 秒，完成后自动刷新</span></div>`;
        if (pollTimer) clearTimeout(pollTimer);
        pollTimer = setTimeout(refreshAll, 2000);   // 处理中强制轮询
      }
    } else if (it.result_url) {
      const iurl = resultUrl(it, it.result_url);
      thumb = iurl
        ? `<a href="${esc(iurl)}" target="_blank" style="display:block;height:100%"><img src="${esc(iurl)}" onerror="imgBroken(this)"></a>`
        : `<div class="vstate">结果已就绪</div>`;
    } else {
      thumb = `<div class="vstate">${esc(it.status)}</div>`;
    }

    const flat = isVideo ? (it.predictions||[]).flatMap(ev => ev.detections||[]) : (it.predictions||[]);
    // 平均置信度：让用户知道模型有多确定
    const avgConf = flat.length ? flat.reduce((s, p) => s + (p.confidence || 0), 0) / flat.length : 0;
    // 虫种分两类：主要检出（is_primary）与「疑似同种」（is_suspect）。
    // 后者来自同一次检测里模型对同批目标给出的另一个低置信度名称 ——
    // 例如同一张图里 3 只稻纵卷叶螟被分别叫成「稻纵卷叶螟」和「叶蝉」。
    // 平级罗列会让用户以为有两种虫，故折叠成一行并显式标注为疑似。
    const chipSet = {}; flat.forEach(p => { const k=p.class; chipSet[k]=chipSet[k]||{n:0,cn:p.class_cn||p.class,suspect:false}; chipSet[k].n++; if (p.is_suspect) chipSet[k].suspect = true; });
    const chipArr = Object.entries(chipSet).sort((a,b) => (a[1].suspect===b[1].suspect) ? 0 : (a[1].suspect?1:-1));
    const mainChips = chipArr.filter(([,v]) => !v.suspect)
      .map(([c,v]) => `<span class="chip ${isVideo?'p':''}" title="${esc(c)}">${esc(v.cn)} ×${v.n}</span>`).join('');
    const susChips = chipArr.filter(([,v]) => v.suspect);
    const suspectChip = susChips.length
      ? `<span class="chip suspect" title="模型对同批目标给出了另一个较低置信度的名称，已折叠以免与主要结论混淆；如需区分请追问或换角度补拍。">疑似同种：${esc(susChips.map(([,v])=>v.cn).join('、'))} ×${susChips.reduce((a,[,v])=>a+v.n,0)}</span>`
      : '';
    const chips = mainChips + suspectChip;
    if (!flat.length && it.status === 'completed') badge = '未检出';
    return `<div class="hcard">
      <div class="hthumb">${thumb}<span class="badge">${badge}</span></div>
      <div class="hbody">
        <div class="name">${esc(it.original_name)}</div>
        <div class="meta">${isVideo
          ? (flat.length ? (it.predictions || []).filter(ev => (ev.detections||[]).length).length + ' 帧检出 · 累计目标 ' + flat.length + ' 次 · 平均置信度 ' + Math.round(avgConf * 100) + '%' : '未检出')
          : (flat.length ? flat.length + ' 个目标 · 平均置信度 ' + Math.round(avgConf * 100) + '%' : '未检出')} · ${d}</div>
        ${chips || (flat.length ? '' : '<span class="chip r">未检出</span>')}
        ${isVideo && it.status === 'completed' ? videoSummary(it) + videoTimeline(it) : ''}
        ${it.error ? `<div class="meta" style="color:var(--rose)">${esc(it.error)}</div>` : ''}
        <div class="analysis">${analysisBlock(it)}</div>
        <div class="fb-row">
          <span class="fb-label">识别准吗？</span>
          <button class="fb-btn ${it.feedback==='good'?'on':''}" onclick="feedback('${it.id}','good')">👍 准</button>
          <button class="fb-btn ${it.feedback==='bad'?'on':''}" onclick="feedback('${it.id}','bad')">👎 不准</button>
        </div>
        <div class="chat" data-did="${it.id}">
          <div class="chat-head" onclick="this.parentElement.classList.toggle('open')">
            💬 继续追问 <span class="chat-arrow">▸</span>
          </div>
          <div class="chat-body">
            <div class="chat-log"></div>
            <div class="chat-in">
              <input placeholder="例如：会传染吗？用什么药？" onkeydown="if(event.key==='Enter')sendChat('${it.id}',this)">
              <button onclick="sendChat('${it.id}',this.previousElementSibling)">发送</button>
            </div>
          </div>
        </div>
        <button class="del" onclick="delItem('${it.id}')">删除</button>
      </div>
    </div>`;
  }).join('');
  // 长文本块：接上滚动提示（未触底时底部渐隐）
  document.querySelectorAll('#historyBox .analysis').forEach(bindScrollHint);
  // 异步拉取每个聊天框的历史（刷新页面后恢复对话）
  document.querySelectorAll('.chat[data-did]').forEach(el => loadChatHistory(el.dataset.did));
  const current = rows.find(r => r.id === currentDetectionId);
  if (current && $('advice')) { $('advice').innerHTML = analysisBlock(current); bindScrollHint($('advice')); }
  const pending = rows.some(r => ['queued','processing'].includes(r.status) || ['queued','processing'].includes(r.analysis_status));
  if (pending) {
    // 有上限地轮询：Worker 没启动时，无上限刷新会让页面永远停在「排队中…」，
    // 用户看不出是慢还是坏了。到点就停手并给出可操作的提示。
    if (pollRounds >= MAX_POLL_ROUNDS) {
      $('pollNote').textContent = ' · 处理时间较长，可刷新查看状态或检查后台日志';
      return;
    }
    pollRounds += 1;
    $('pollNote').textContent = ' · 识别或建议正在处理中，稍后自动刷新';
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(refreshAll, 3000);
  } else {
    pollRounds = 0;
    $('pollNote').textContent = '';
  }
}

// 视频结果采用「点击才加载」：避免历史列表一次插入多个 <video> 触发 onerror 误报，
// 也避免同时发几十个 mp4 请求把带宽打满
document.addEventListener('click', e => {
  const wrap = e.target.closest('.vwrap');
  if (!wrap || wrap.dataset.playing) return;
  wrap.dataset.playing = '1';
  const v = document.createElement('video');
  v.src = wrap.dataset.src;
  v.controls = true;
  v.autoplay = true;
  v.playsInline = true;
  v.preload = 'auto';
  v.style.cssText = 'width:100%;height:100%;object-fit:contain;background:#000';
  v.onerror = () => {
    wrap.innerHTML = '<div class="vstate vfail">视频无法播放<br><span>格式不受浏览器支持或文件已被清理</span></div>';
  };
  wrap.innerHTML = '';
  wrap.appendChild(v);
});

async function delItem(id) {
  if (!confirm('确认删除这条记录？')) return;
  try { await api('/detections/' + id, { method:'DELETE' }); refreshAll(); }
  catch (e) { alert('删除失败：' + e.message); }
}

async function feedback(id, rating) {
  try {
    await api('/detections/' + id + '/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating })
    });
    refreshAll();
  } catch (e) { alert('提交失败：' + e.message); }
}

async function clearAllData() {
  if (!confirm('清空全部记录？此操作不可恢复。')) return;
  try {
    await api('/detections/all', { method: 'DELETE' });
    toast('已清空全部记录', true);
    await refreshAll();
  } catch (e) { alert('清空失败：' + e.message); }
}

async function loadChatHistory(did) {
  try {
    const history = await api('/detections/' + did + '/chat');
    if (!history.length) return;
    document.querySelectorAll(`.chat[data-did="${did}"]`).forEach(chat => {
      const log = chat.querySelector('.chat-log');
      log.innerHTML = history.map(m =>
        `<div class="chat-msg ${m.role === 'user' ? 'u' : 'a'}">${esc(m.content)}</div>`
      ).join('');
      log.scrollTop = log.scrollHeight;
    });
  } catch (e) { /* 历史拉取失败静默，不影响主流程 */ }
}

// ===== AI 追问聊天 =====
function renderChatBox(container, did, withGreeting) {
  container.style.display = 'block';
  container.innerHTML = `
    <div class="chat" data-did="${did}">
      <div class="chat-head">💬 继续追问（Agent 对话）</div>
      <div class="chat-log">
        ${withGreeting ? '<div class="chat-msg sys">可以继续问我：会传染吗？用什么药？什么时候打？</div>' : ''}
      </div>
      <div class="chat-in">
        <input placeholder="继续提问…" onkeydown="if(event.key==='Enter')sendChat('${did}',this)">
        <button onclick="sendChat('${did}',this.previousElementSibling)">发送</button>
      </div>
    </div>`;
}

async function sendChat(did, input) {
  const q = input.value.trim();
  if (!q) return;
  const chat = input.closest('.chat');
  const log = chat.querySelector('.chat-log');
  const btn = chat.querySelector('button');
  log.innerHTML += `<div class="chat-msg u">${esc(q)}</div>`;
  input.value = ''; btn.disabled = true;
  const thinking = document.createElement('div');
  thinking.className = 'chat-msg sys'; thinking.textContent = '思考中…';
  log.appendChild(thinking);
  log.scrollTop = log.scrollHeight;
  try {
    const r = await api('/detections/' + did + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: q })
    });
    thinking.remove();
    log.innerHTML += `<div class="chat-msg a">${esc(r.reply)}</div>`;
  } catch (e) {
    thinking.remove();
    const msg = (e && e.message) ? e.message : JSON.stringify(e);
    log.innerHTML += `<div class="chat-msg sys">${esc('AI 暂时无法回答：' + msg)}</div>`;
  }
  btn.disabled = false;
  log.scrollTop = log.scrollHeight;
}


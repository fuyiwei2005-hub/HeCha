const MAX_IMG = 10 * 1024 * 1024, MAX_VID = 100 * 1024 * 1024;
function checkFile(file, isVideo) {
  const limit = isVideo ? MAX_VID : MAX_IMG;
  const okTypes = isVideo
    ? ['video/mp4', 'video/webm', 'video/quicktime']
    : ['image/jpeg', 'image/png', 'image/webp'];
  if (!okTypes.includes(file.type)) {
    return isVideo ? '请选择 MP4 / WebM / MOV 视频' : '请选择 JPG / PNG / WebP 图片';
  }
  if (file.size > limit) {
    return `文件过大：${(file.size / 1048576).toFixed(1)}MB，上限 ${limit / 1048576}MB`;
  }
  if (file.size === 0) return '文件为空，请重新选择';
  return null;
}

// ── 作物上下文（寄主先验） ────────────────────────────────────────────
const CROP_STORE_KEY = 'pg_crop';

/** 结果卡片上的先验徽章：让用户看见「为什么它排第一」。 */
function priorBadge(v) {
  const p = v.prior;
  if (!p || !p.level || p.level === 'neutral') return '';
  const TXT = {
    strong: '✓ 本作物常见虫种 · 已加权',
    related: '✓ 同类作物可见 · 轻度加权',
    conflict: '⚠ 非本作物典型虫种 · 已降权保留',
  };
  const txt = TXT[p.level];
  if (!txt) return '';
  // 变化时把「原始 → 加权」摊开给用户看，避免觉得系统在偷偷改分
  const extra = (typeof v.raw === 'number' && Math.abs(v.max - v.raw) > 0.0001)
    ? `（原始 ${Math.round(v.raw * 100)}% → ${Math.round(v.max * 100)}%）` : '';
  return `<span class="prior-tag ${p.level}">${txt}${extra}</span>`;
}

async function loadCrops() {
  const sel = $('cropSel');
  if (!sel) return;
  // 接口需要登录；游客态先给个说明，登录后由 refreshAll 重新加载
  if (!localStorage.getItem('token')) {
    sel.innerHTML = '<option value="">登录后可指定作物</option>';
    sel.disabled = true;
    return;
  }
  try {
    const d = await api('/detections/crops');
    if (!d.available || !d.crops || !d.crops.length) {
      sel.innerHTML = '<option value="">暂不可用</option>';
      sel.disabled = true;
      $('cropTip').textContent = d.error
        ? '作物上下文暂不可用：' + d.error
        : '当前没有可用的作物数据，不指定也能正常检测。';
      return;
    }
    const boosted = d.crops.filter(c => c.has_prior);
    const ctxOnly = d.crops.filter(c => !c.has_prior);
    let html = '<option value="">不指定（不影响检测）</option>';
    if (boosted.length) {
      html += '<optgroup label="可校正识别排序">' + boosted.map(c =>
        `<option value="${esc(c.key)}" data-label="${esc(c.label)}">${esc(c.label)} · ${c.strong_count + c.related_count} 种常见害虫</option>`
      ).join('') + '</optgroup>';
    }
    if (ctxOnly.length) {
      html += '<optgroup label="优化 AI 建议口径">' + ctxOnly.map(c =>
        `<option value="${esc(c.key)}" data-label="${esc(c.label)}">${esc(c.label)}</option>`
      ).join('') + '</optgroup>';
    }
    sel.innerHTML = html;
    sel.disabled = false;
    sel.onchange = updateCropTip;
    const saved = localStorage.getItem(CROP_STORE_KEY) || '';
    if (saved && Array.prototype.some.call(sel.options, o => o.value === saved)) sel.value = saved;
    updateCropTip();
  } catch (e) {
    sel.innerHTML = '<option value="">加载失败</option>';
    sel.disabled = true;
    $('cropTip').textContent = '作物上下文加载失败，不影响正常检测（不指定即可）。';
  }
}

function updateCropTip() {
  const sel = $('cropSel'), tip = $('cropTip');
  if (!sel || !tip) return;
  const key = sel.value;
  if (!key) {
    tip.textContent = '告知作物可让系统结合寄主规律校正识别、并生成更贴合的建议；不指定也能正常使用。';
    try { localStorage.removeItem(CROP_STORE_KEY); } catch (x) {}
    return;
  }
  const opt = sel.selectedOptions && sel.selectedOptions[0];
  // 提示语要用显示名（李 -> 李子）；直接用 value 会出现下拉框显示「李子」、
  // 提示行却写「李」的自相矛盾
  const name = (opt && opt.dataset && opt.dataset.label) || key;
  const inBoost = opt && opt.parentNode && opt.parentNode.label === '可校正识别排序';
  // 「不会被删除」这句话必须写清楚：这是用户对「AI 会不会漏报」最大的顾虑
  tip.textContent = inBoost
    ? `已选择「${name}」：该作物的常见虫种会加权排前。即使结果与该作物不符也不会被删除，只会降权并提示复核。`
    : `已选择「${name}」：暂无该作物虫种先验，不改排序，但 AI 建议会按此作物给出用药部位与安全间隔期口径。`;
  try { localStorage.setItem(CROP_STORE_KEY, key); } catch (x) {}
}


async function uploadImage(file) {
  if (!requireLogin()) return;
  const bad = checkFile(file, false);
  if (bad) { showMsg('upMsg', bad, false); return; }
  showMsg('upMsg', '正在上传并检测…', true);
  const fd = new FormData(); fd.append('file', file);
  const crop = ($('cropSel') && $('cropSel').value) || '';
  // crop 必须是表单文本字段，不能塞进 file —— 走 Blob 会让后端 Form(None) 直接 422
  if (crop) fd.append('crop', crop);
  try {
    const r = await api('/detections/image', { method: 'POST', body: fd });
    // 填控制台
    if (r.result_url) {
      const ticket = await fetchResultTicket(r.id).catch(() => null);
      if (ticket) {
        $('stageImg').src = ticket;
        $('stageImg').style.display = 'block';
        $('stagePh').style.display = 'none';
      }
    }
    $('anSub').textContent = (r.original_name || '图片') + ' · 已处理';
    // 解析结果
    const preds = r.predictions || [];
    if (preds.length) {
      const byClass = {};
      preds.forEach(p => byClass[p.class] = (byClass[p.class]||{n:0,max:0,cn:p.class_cn||p.class,prior:p.prior,raw:p.raw_confidence,suspect:false}));
      preds.forEach(p => { const b = byClass[p.class]; b.n++; b.max = Math.max(b.max, p.confidence); if (p.is_suspect) b.suspect = true; });
      // 疑似同种排最后并加标注：不让一个低置信度的变体与主要结论平级展示
      const ordered = Object.entries(byClass).sort((a,b) => (a[1].suspect===b[1].suspect) ? 0 : (a[1].suspect?1:-1));
      $('resList').innerHTML = ordered.map(([c,v]) => `
        <div class="res-card${v.suspect?' suspect':''}">
          <div class="r-top"><span class="r-name">${v.suspect?'疑似同种 · ':''}${esc(v.cn)}</span><span class="r-n">×${v.n}</span></div>
          ${v.cn !== c ? '<div style="font-size:11px;color:var(--muted-2);margin-top:2px">'+esc(c)+'</div>' : ''}
          <div class="bar"><i data-w="${Math.round(v.max*100)}"></i></div>
          ${v.suspect ? '<div style="font-size:11px;color:var(--muted-2);margin-top:4px">模型对同批目标给出了另一个较低置信度的名称</div>' : priorBadge(v)}
        </div>`).join('');
      setTimeout(() => document.querySelectorAll('#resList .bar i').forEach(b => b.style.width = b.dataset.w + '%'), 100);
    } else {
      $('resList').innerHTML = '<div class="res-card"><div class="r-top"><span class="r-name">未检出目标</span></div><div class="bar"><i style="width:15%"></i></div></div>';
    }
    currentDetectionId = r.id; pollRounds = 0;
    $('advice').innerHTML = analysisBlock(r);
    bindScrollHint($('advice'));
    // 渲染聊天框（控制台位置）
    renderChatBox($('chatBox'), r.id, true);
    showMsg('upMsg', '检测完成 ✓', true);
    refreshAll();
  } catch(e) { showMsg('upMsg', '检测失败：' + e.message, false); }
}

async function uploadVideo(file) {
  if (!requireLogin()) return;
  const bad = checkFile(file, true);
  if (bad) { alert(bad); return; }
  const fd = new FormData(); fd.append('file', file);
  try {
    const r = await api('/videos', { method: 'POST', body: fd });
    // 拿到 id 后直接盯着这一条，不用等列表轮询；后端超时兜底会给明确失败原因
    pollVideo(r.id);
    alert('视频已入队，Worker 处理中，下方历史里可实时看到进度。');
    refreshAll();
  }
  catch(e) { alert('视频提交失败：' + e.message); }
}

// 单条视频任务轮询：有明确终点，不会像「整个列表反复刷新」那样永远转圈
async function pollVideo(id, tries = 0) {
  const MAX_TRIES = 60;   // 2s × 60 ≈ 2 分钟，后端 15 分钟兜底之前先给用户反馈
  try {
    const it = await api('/detections/' + id);
    if (it.status === 'completed' || it.status === 'failed') { refreshAll(); return; }
  } catch (e) { refreshAll(); return; }
  if (tries >= MAX_TRIES) { refreshAll(); return; }
  setTimeout(() => pollVideo(id, tries + 1), 2000);
}

// 结果加载失败时的占位。图片与视频要分开说，否则视频一旦触发 onerror
// 会被误报成「结果图已被清理」——文件其实完好。

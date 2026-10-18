async function loadStats() {
  try {
    const s = await api('/statistics');
    const top = s.classes && s.classes[0] ? s.classes[0] : null;
    const data = [
      ['已识别害虫', s.total_objects, '个'],
      ['覆盖虫种', s.classes ? s.classes.length : 0, '种'],
      ['检测次数', s.total_jobs, '次'],
      ['最多虫种', top ? (top.name_cn || top.name).split('(')[0] : '—', top ? '×' + top.count : '']
    ];
    $('stats').innerHTML = data.map(([l,v,unit]) => `
      <div class="stat"><div class="n">${v}<span style="font-size:13px;font-weight:400;color:var(--muted-2)"> ${unit}</span></div><div class="l">${l}</div>
      <div class="bars">${[40,70,55,85,60,90].map(h=>`<i style="height:${h}%"></i>`).join('')}</div></div>`).join('');
  } catch(e) {
    // 原先是空 catch：接口 401 或后端异常时统计区会一直空白，而上方标题写着
    // 「当前账号的累计检测数据」，看上去像页面坏了。这里改成可读的明确占位。
    const guest = !localStorage.getItem('token');
    renderStatsPlaceholder(
      guest ? '登录后即可查看你的累计识别统计与虫种分布' : '统计数据加载失败：' + e.message,
      !guest
    );
  }
}

// 统计区占位：游客态与异常态共用，避免出现「有标题、无内容」的空白区块
function renderStatsPlaceholder(text, isErr) {
  if (!$('stats')) return;
  $('stats').innerHTML = '<div class="stat-empty' + (isErr ? ' err' : '') + '">' + text + '</div>';
}

async function refreshAll() {
  if (!localStorage.getItem('token')) return;
  if ($('loginNote')) $('loginNote').hidden = true;
  if ($('stats')) await loadStats();
  try {
    if ($('historyBox')) await loadHistory();
    if (PAGE_NAME === 'detect' && currentDetectionId) {
      const it=await api('/detections/' + currentDetectionId);
      $('advice').innerHTML=analysisBlock(it); bindScrollHint($('advice'));
      if (['queued','processing'].includes(it.analysis_status) && pollRounds++ < MAX_POLL_ROUNDS) {
        clearTimeout(pollTimer); pollTimer=setTimeout(refreshAll,2000);
      }
    }
  } catch(e) { /* api() handles session expiry and errors */ }
}



if ($('infoPage')) {
 const cfg=INFO_PANELS[PAGE_NAME==='deployment'?'source':PAGE_NAME];
 $('infoPageTitle').textContent=cfg.title;
 $('infoPageBody').innerHTML='<p class="im-sub">'+cfg.sub+'</p><dl class="im-kv">'+cfg.rows.map(r=>'<dt>'+r[0]+'</dt><dd>'+r[1]+'</dd>').join('')+'</dl><p class="im-note">'+cfg.note+'</p>'+(PAGE_NAME==='contact'?'<button class="im-btn" onclick="copyEmail(this)">复制邮箱</button>':'');
}
fetch('/api/health').then(r=>r.json()).then(h=>{
 const b=document.createElement('div'); b.id='runtimeStatus';
 b.style.cssText='position:relative;padding:10px 20px;background:#fff3cd;color:#664d03;text-align:center;font-size:13px;z-index:100';
 const mode=h.detector==='yolo'?'真实识别模型已启用':h.detector==='mock'?'当前为演示模式，未启用真实识别模型':'识别模型未就绪，请检查后台日志';
 b.textContent=mode+' · '+(h.llm==='configured'?'AI 服务已配置':'AI 服务未配置')+' · '+(h.task_backend==='local'?'本地任务处理':'队列任务处理');
 document.body.prepend(b);
}).catch(()=>{});

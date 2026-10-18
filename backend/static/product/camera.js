
let camStream = null;

// 浏览器只在「安全上下文」给摄像头权限：https、localhost、127.0.0.1。
// 公网 http（如 http://<服务器IP>:8000）下 mediaDevices 直接是 undefined，
// 点拍照只会抛一句英文 TypeError —— 所以先探测，不可用就把按钮摆成禁用态并说明原因。
function cameraAvailable() {
  return !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

function initCameraButton() {
  const btn = document.getElementById('camBtn');
  if (!btn || cameraAvailable()) return;
  btn.disabled = true;
  btn.style.opacity = '.45';
  btn.style.cursor = 'not-allowed';
  btn.textContent = '📸 拍照（需 HTTPS）';
  btn.title = '当前通过 HTTP 访问，浏览器出于安全策略禁止调用摄像头。请用 https:// 域名或本机 localhost 打开，或直接上传图片。';
}

function cameraHint() {
  const host = location.host;
  toast('当前是 HTTP 访问（' + host + '），浏览器禁止调用摄像头。'
        + '用 https:// 域名或本机 localhost 打开即可拍照，现在可以先用「选择图片」上传。', false);
}

async function openCamera() {
  if (!cameraAvailable()) { cameraHint(); return; }
  if (!requireLogin()) return;   // 游客点了拍照，先带到登录卡片，别白等一次 401
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
    document.getElementById('camVideo').srcObject = camStream;
    document.getElementById('camModal').style.display = 'flex';
  } catch(e) {
    // 常见三种：用户拒绝授权、没有摄像头设备、被其它程序占用。分开说清楚，
    // 否则一句 NotAllowedError 用户完全不知道下一步该干嘛。
    let msg = e && e.message ? e.message : String(e);
    if (e && e.name === 'NotAllowedError') msg = '摄像头权限被拒绝，请在浏览器地址栏的权限图标里允许摄像头后重试';
    else if (e && e.name === 'NotFoundError') msg = '没有检测到摄像头设备';
    else if (e && e.name === 'NotReadableError') msg = '摄像头被其它程序占用，请先关闭占用它的软件';
    toast('无法打开摄像头：' + msg, false);
  }
}
function closeCamera() {
  if (camStream) { camStream.getTracks().forEach(t => t.stop()); camStream = null; }
  document.getElementById('camModal').style.display = 'none';
}
function snapPhoto() {
  const v = document.getElementById('camVideo');
  // 摄像头还没出画面时 videoWidth 是 0，此时 drawImage 会得到一张空白图并直接上传，
  // 结果就是「拍照识别没有任何结果」却没有任何报错。
  if (!v.videoWidth || !v.videoHeight) { toast('摄像头画面还没准备好，请稍等一秒再拍', false); return; }
  const c = document.getElementById('camCanvas');
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext('2d').drawImage(v, 0, 0);
  c.toBlob(async (blob) => {
    closeCamera();
    const file = new File([blob], 'camera_snap.jpg', { type: 'image/jpeg' });
    await uploadImage(file);
  }, 'image/jpeg', 0.92);
}

// 摄像头能力探测放在本块末尾：函数在本块里定义，主脚本块执行时它还不存在，
// 放前面会 ReferenceError 并打断整段启动逻辑（登录卡片就再也显示不出来了）。
initCameraButton();

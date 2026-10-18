/** Shared request boundary. Mutations are never automatically retried. */
async function api(path, opts = {}) {
  const token = localStorage.getItem('token');
  const headers = new Headers(opts.headers);
  if (token) headers.set('Authorization', 'Bearer ' + token);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), opts.body instanceof FormData ? 120000 : 30000);
  const abort = () => controller.abort();
  if (opts.signal) {
    opts.signal.addEventListener('abort', abort, { once: true });
    if (opts.signal.aborted) controller.abort();
  }
  try {
    const response = await fetch('/api' + path, { ...opts, headers, signal: controller.signal });
    if (response.status === 401 && !path.startsWith('/auth/')) {
      const message = token ? '登录已过期，请重新登录' : '请先登录后再使用该功能';
      softLogout(message);
      throw new Error(message);
    }
    if (response.status === 204) return null;
    let body;
    try { body = await response.json(); }
    catch (error) {
      if (controller.signal.aborted) throw error;
      throw new Error('服务返回了无法读取的结果，请稍后重试');
    }
    if (!response.ok) {
      const detail = body && body.detail;
      const message = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : '请求失败（' + response.status + '）';
      throw new Error(message);
    }
    return body;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('请求超时或已取消，请刷新记录确认处理结果');
    if (error instanceof TypeError) throw new Error('网络连接失败，请检查服务连接后重试');
    throw error;
  } finally {
    clearTimeout(timeout);
    if (opts.signal) opts.signal.removeEventListener('abort', abort);
  }
}

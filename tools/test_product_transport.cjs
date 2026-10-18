const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../backend/static/product/transport.js'), 'utf8');
let handler, token = 'test-session', logout = 0, immediateTimeout = false;
const context = vm.createContext({Headers, FormData, AbortController, Error, TypeError, JSON,
  localStorage: {getItem: () => token}, softLogout: () => { logout++; },
  setTimeout: (fn, ms) => setTimeout(fn, immediateTimeout ? 1 : ms), clearTimeout,
  fetch: (...args) => handler(...args)});
vm.runInContext(source, context);
const api = context.api;
const response = (status, value) => ({status, ok: status >= 200 && status < 300, json: async () => value});
(async () => {
  const input = new Headers({'X-Trace': 'test'});
  handler = async (url, opts) => {
    assert.equal(url, '/api/detections');
    assert.equal(opts.headers.get('Authorization'), 'Bearer test-session');
    assert.equal(opts.headers.get('X-Trace'), 'test');
    return response(200, {ok: true});
  };
  assert.equal((await api('/detections', {headers: input})).ok, true);
  assert.equal(input.has('Authorization'), false);
  handler = async () => response(401, {});
  await assert.rejects(api('/detections'), /登录已过期/);assert.equal(logout, 1);
  await assert.rejects(api('/auth/login'), /请求失败/);assert.equal(logout, 1);
  handler = async () => response(422, {detail: 'invalid file'});
  await assert.rejects(api('/detections'), /invalid file/);
  handler = async () => response(204, null);assert.equal(await api('/detections'), null);
  handler = async () => { throw new TypeError('network'); };
  await assert.rejects(api('/detections'), /网络连接失败/);
  handler = async () => ({status: 200, ok: true, json: async () => { throw new SyntaxError(); }});
  await assert.rejects(api('/detections'), /无法读取/);
  immediateTimeout = true;
  handler = (_, opts) => new Promise((_, reject) => opts.signal.addEventListener('abort', () => reject(new Error('aborted'))));
  await assert.rejects(api('/detections'), /请求超时或已取消/);
  immediateTimeout = false;
  handler = async (_, opts) => { assert.equal(opts.signal.aborted, true);throw new Error('aborted'); };
  const cancel = new AbortController();cancel.abort();
  await assert.rejects(api('/detections', {signal: cancel.signal}), /请求超时或已取消/);
  console.log('PASS request headers, session expiry, validation, empty response, network, malformed response, timeout and cancellation');
})().catch(error => {console.error(error);process.exitCode = 1;});

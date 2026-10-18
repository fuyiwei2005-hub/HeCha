import { BrandMark } from './Icon'
import { FormEvent, useState } from 'react'
import { friendly, login, register } from '../api'

export function LoginPage({ onAuthed }: { onAuthed: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // 后端是 username 登录（不是邮箱）；此前的 React 版用 type=email 收.login()却不匹配，
  // 用户填真实邮箱永远登不上，是一处静默的可用性陷阱。这里改成文本输入并统一口径。
  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    const name = account.trim()
    if (!name || !password) { setError('请输入账号和密码'); return }
    if (mode === 'register' && (name.length < 3 || name.length > 32)) {
      setError('账号需为 3-32 位')
      return
    }
    if (mode === 'register' && password.length < 6) { setError('密码至少 6 位'); return }

    setBusy(true)
    try {
      if (mode === 'register') {
        await register(name, password)
      }
      await login(name, password)
      onAuthed()
    } catch (err) {
      const raw = friendly(err)
      // 已注册是注册流程里最常见的失败，给一句能直接行动的话而不是后端原文
      setError(/already/i.test(raw) ? '该账号已被占用，请换一个或直接登录' : raw)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <div className="auth-card rise">
        <div className="auth-head">
          <span className="auth-brand"><BrandMark/></span><p className="eyebrow">禾察 · HECHA</p>
          <h1>{mode === 'login' ? '欢迎回来' : '创建账号'}</h1>
          <p className="muted" style={{ fontSize: '0.875rem' }}>
            农作物害虫智能识别与植保决策平台
          </p>
        </div>

        <form id="authForm" className="auth-form" onSubmit={submit}>
          <label className="field">
            <span>账号</span>
            <input
              id="username" className="input"
              value={account}
              onChange={(e) => setAccount(e.target.value)}
              placeholder="3-32 位字母、数字或下划线"
              autoComplete="username"
              autoFocus
            />
          </label>

          <label className="field">
            <span>密码</span>
            <input
              id="password" className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === 'register' ? '至少 6 位' : '请输入密码'}
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
            />
          </label>

          {error && <div className="alert alert-error">{error}</div>}

          <div className="auth-actions">
            <button className="btn btn-block" type="submit" disabled={busy}>
              {busy ? <span className="spinner" /> : null}
              {busy ? '处理中…' : mode === 'login' ? '登录' : '注册并登录'}
            </button>
            <button
              className="btn btn-ghost btn-block"
              type="button"
              disabled={busy}
              onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}
            >
              {mode === 'login' ? '没有账号？去注册' : '已有账号？去登录'}
            </button>
          </div>
        </form>

        <p className="auth-hint">
          上传一张叶片或田间照片，系统会定位虫体、识别虫种，并生成带知识库溯源的防治建议。
        </p>
      </div>
    </div>
  )
}

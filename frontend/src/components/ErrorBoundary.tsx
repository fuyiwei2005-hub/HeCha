import { Component, ErrorInfo, ReactNode } from 'react'

type Props = { children: ReactNode }
type State = { error: Error | null }

/**
 * 顶层错误边界。
 *
 * 没有它时，任何一个渲染期的 TypeError（例如后端某个字段改名、
 * 返回 null）都会让 React 卸载整棵树 —— 用户看到纯白屏，
 * 连"出错了"的提示都没有，只能自己想到去刷新。
 * 这里至少给一个可操作的出口。
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 保留控制台线索，方便现场排查（不发送到任何远端）
    console.error('界面渲染出错：', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div
        role="alert"
        style={{
          minHeight: '100vh', display: 'grid', placeItems: 'center',
          padding: '32px', textAlign: 'center',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
          background: '#f4f2ea', color: '#173f34',
        }}
      >
        <div style={{ maxWidth: 520 }}>
          <h1 style={{ fontSize: 20, margin: '0 0 10px' }}>页面出了点问题</h1>
          <p style={{ color: '#56846b', lineHeight: 1.7, margin: '0 0 18px' }}>
            数据可能来自旧版本后端，或本次响应不完整。<br />
            先刷新试试；如果一直这样，请把下面的信息反馈给开发者。
          </p>
          <pre
            style={{
              textAlign: 'left', fontSize: 12, lineHeight: 1.6, overflow: 'auto',
              background: '#fff', border: '1px solid #d8e0da', borderRadius: 10,
              padding: '10px 12px', maxHeight: 180, color: '#8a4b4b',
            }}
          >
            {error.name}: {error.message}
          </pre>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: 16, padding: '10px 22px', borderRadius: 24, border: 'none',
              background: '#173f34', color: '#fff', fontSize: 14, cursor: 'pointer',
            }}
          >
            刷新页面
          </button>
        </div>
      </div>
    )
  }
}

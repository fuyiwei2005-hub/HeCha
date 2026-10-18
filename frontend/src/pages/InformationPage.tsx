import { Icon } from '../components/Icon'
import { Link } from 'react-router-dom'
const entries: Record<string, {intro: string; rows: [string,string][]}> = {
  features: {intro: '从田间影像到可追溯的植保建议。', rows: [['图片识别','上传照片、拍照识别、查看虫种及置信度。'],['视频识别','后台逐帧检测、结果播放和检出时间线。'],['作物上下文','选择作物，辅助候选排序与建议生成。'],['AI 建议','结合检测结果和植保知识库生成建议，支持资料引用及追问。'],['记录管理','历史结果、反馈、下载和个人统计。']]},
  about: {intro: '识别结果和 AI 分析独立保存，建议生成失败时仍能查看检测结果。',rows: [['1 · 采集','上传图片、拍照或提交视频。'],['2 · 视觉检测','YOLO 模型定位虫体，输出类别、置信度及标注结果。'],['3 · 知识检索','按检测结果检索本地植保知识库。'],['4 · 分析','DeepSeek 根据检测与资料生成建议，视频任务在后台执行。'],['5 · 复核','查看资料、继续追问，并记录反馈。']]},
  deployment: {intro: '本地运行和服务器运行使用同一组业务接口。',rows: [['前端','React + TypeScript + Vite；独立页面路由和统一数据查询。'],['后端','FastAPI + SQLAlchemy + Alembic。'],['本地运行','SQLite 数据库和本地后台任务执行器。'],['多人部署','可使用 PostgreSQL、Redis 和独立 Worker，部署前需验证资源配置。'],['视觉与视频','项目随附 YOLO 权重，FFmpeg 处理视频。'],['AI 分析','后端读取本地配置连接 DeepSeek，页面不接触密钥。']]},
}
export function InformationPage({page}: {page: string}) {
  const entry = entries[page]

  return <section id="infoPage" className={"information-page information-"+page}><div className="information-intro"><span className="info-symbol"><Icon index={page === 'deployment' ? 9 : 7}/></span><p className="eyebrow">{page === 'deployment' ? '简洁的体验，扎实的底层。' : '了解禾察'}</p><h2>{page === 'deployment' ? '从本地启程，向田间延伸。' : entry.intro}</h2>{page === 'deployment' && <p>{entry.intro}</p>}</div><dl className="info-grid">{entry.rows.map(([label,description],index) => <div className="info-tile" key={label}><span className="info-number">{String(index+1).padStart(2,'0')}</span><dt>{label}</dt><dd>{description}</dd></div>)}</dl>
    {page === 'deployment' && <a href="/docs" target="_blank" rel="noopener">查看 API 文档 →</a>}
    {page === 'features' && <Link className="btn" to="/detect">开始图片识别</Link>}
  </section>
}

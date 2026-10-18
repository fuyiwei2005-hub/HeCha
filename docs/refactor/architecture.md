# 禾察重构进度与功能基线

## 已落地：React 页面迁移

默认产品入口使用 React + TypeScript + Vite。独立路由与公共侧栏由 React Router 管理，TanStack Query 统一接口缓存与任务轮询。
登录、首页、图片、视频、记录、统计与介绍页面分别实现；图片和视频入口分开。反馈状态、作物选择和历史追问支持刷新恢复。
会话先验证再展示页面，网络故障支持重试；退出时清理查询缓存。
旧页面保留用于回退：PRODUCT_FRONTEND=legacy；构建不存在时也可运行旧页面。

生产页面目录：frontend/src/pages；公共布局：components/AppLayout.tsx；统一查询：hooks/useRecords.ts；入口与会话：App.tsx。
验证入口：tools/browser_react.cjs，使用模拟检测与 AI，执行实际本地后台任务。真实 DeepSeek 配置和模型权重保持原配置。


## 已落地：模块化基础

以下为上一阶段形成的旧版回退实现；默认产品入口已切换为 React，路由地址保持一致。

- backend/static/index.html：公共页面骨架与弹窗。
- backend/templates/product/：按页面拆分的内容；manifest.json 声明页面归属。
- backend/static/product/app.css：共享样式。
- backend/static/product/shared.js：状态和结果建议渲染。
- transport.js：统一接口请求、30 秒普通请求与 120 秒上传超时、取消与错误处理；session.js：会话及结果下载票据。
- uploads.js：上传、作物选择和视频进度；results.js：记录、对话和反馈。
- statistics.js：统计及刷新；information.js：项目介绍；authentication.js：登录注册及启动。
- camera.js、navigation.js、service-status.js：摄像头、折叠菜单与服务状态。
- backend/app/api/health.py：运行依赖检查，接口保持 /api/health。

脚本暂时按固定顺序加载，以兼容现有页面事件；并非已经完成 ES 模块或 React 迁移。
静态资源附内容指纹，页面更新后不会继续使用旧脚本。React 构建已成为当前产品入口；这些脚本仅用于旧页面回退。

## 功能验收基线

| 模块 | 必须保留的行为 |
| --- | --- |
| 登录 | 首访登录、注册、失效跳转、返回原模块、退出 |
| 图片 | 作物选择、上传、拍照、标注图、AI 建议、重试、资料引用 |
| 视频 | 上传、任务状态、视频专属记录、时间线、结果播放 |
| 历史 | 刷新恢复、追问及对话记录、反馈、单条删除、清空确认 |
| 统计 | 当前账号统计、独立路由 |
| 公共 | 禾察品牌、左侧折叠菜单、键盘操作、手机适配、页面刷新和前进后退 |

验证入口：backend/tests 与 tools/browser_pages.cjs。浏览器测试使用隔离数据库、模拟模型和模拟 AI，执行真实本地任务调度；不验证模型准确率或真实 DeepSeek 质量。

## 后续阶段

1. 已完成公共布局、登录和各模块的 React 迁移与默认入口切换。
2. 已引入路由及统一查询层，历史页已使用后端分页与条件筛选。
3. 整理识别和分析业务服务、任务进度及重试规则，补齐幂等与并发场景。
4. 固定依赖并提供本地与多人部署方案；多人部署再验证 PostgreSQL 和 Redis。

每个阶段独立验证，不把更换框架等同于完成重构。

历史分页、任务进度与恢复的实现及验证边界见 [升级说明](history-task-upgrade.md)。

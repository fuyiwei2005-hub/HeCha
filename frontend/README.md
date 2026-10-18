# 禾察前端

React + TypeScript + Vite，使用 React Router 管理独立页面，TanStack Query 管理接口缓存、任务轮询和数据刷新。

## 页面

`/` 首页；`/login` 登录注册；`/detect` 图片与拍照；`/video` 视频；`/history` 记录、追问和反馈；`/statistics` 统计；`/features`、`/about`、`/deployment` 介绍页面。

默认入口在构建存在时使用 React。`/experimental/` 提供相同前端的预览入口并支持深链接。
`PRODUCT_FRONTEND=legacy` 可暂时恢复旧页面；缺少构建时自动回退。旧代码留作兼容，不能再分别增加两套产品功能。

## 开发与构建

安装依赖：`npm ci`；开发：`npm run dev`；构建及类型检查：`npm run build`。
Vite 将 `/api` 代理给本地 8000 端口的后端。生产运行需要保留 `frontend/dist`，后端按页面路由返回入口文件。

## 数据与会话

会话验证成功后才展示功能页面。过期跳转登录并返回原页面；网络故障可重试，不直接清空登录状态。
退出或更换账号时清理查询缓存；只在识别或分析任务未完成时轮询记录。上传不自动重试，避免重复提交。

## 验证

`tools/browser_react.cjs` 使用隔离数据库、模拟模型与模拟 AI，覆盖登录回跳、模块路由、上传、异步分析重试、参考资料、追问、反馈、视频、拍照和移动页面。

历史页使用服务端分页，筛选与页码保存在 URL。视频卡片提供阶段、帧数和失败重试；新增验证入口为 tools/browser_records.cjs。

首页底部 `/#contact` 提供联系我们。左侧采用全高抽屉导航；首页含原生滚动驱动场景，页面切换使用可取消的短过渡，支持减少动态效果。

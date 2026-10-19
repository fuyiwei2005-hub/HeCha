# 禾察：智能植保决策平台

默认前端已迁移到 React + TypeScript + Vite。React Router 管理独立模块页面，TanStack Query 管理查询缓存、刷新和后台任务轮询。
保留 FastAPI、SQLAlchemy、定制 YOLO 运行时和 DeepSeek 分析；本地任务可在无 Redis 环境运行。

首页 `/`、登录 `/login`、图片 `/detect`、视频 `/video`、历史 `/history`、统计 `/statistics`，以及核心能力、技术介绍和部署页面均支持直接访问与刷新。“联系我们”位于首页底部，模型说明页面已移除。
首次访问先登录；直接访问模块时，登录后返回原模块。左侧全高抽屉支持展开、收起、等高导航和键盘操作；页面切换带统一过渡，首页以滚动旋转的藤蔓和六片害虫叶片展示功能入口；点击叶片展开功能卡片。手机、键盘和减少动态效果设置均可使用。

图片识别结果与 AI 建议独立保存；建议失败时保留识别结果并支持重试。历史追问、反馈和作物选择支持刷新恢复。
详情见 [前端说明](frontend/README.md) 与 [架构进度](docs/refactor/architecture.md)。

历次验证包括 188 项后端测试、28 项 React 浏览器检查、6 项导航专项检查及 14 项分页／视频进度检查；浏览器检查采用隔离数据和模拟检测／AI，执行实际本地后台任务。
`PRODUCT_FRONTEND=legacy` 可切回旧页面；缺少 React 构建时自动回退。`/experimental/` 保留同一 React 前端的预览入口。

历史记录已支持分页、关键词／日期／类型／状态筛选；视频任务支持帧进度显示和保留源文件重试。详见 [升级说明](docs/refactor/history-task-upgrade.md)。

## 本地启动

首次克隆后，请先按下方步骤安装依赖并构建前端。完成后在仓库根目录执行：

```powershell
.\start.ps1
```

打开 `http://127.0.0.1:8000/`。按 Ctrl+C 关闭本项目启动的进程；端口被占用时可加 `-Port 8010`。

桌面版默认使用本地任务处理器，图片、视频和 AI 建议不依赖 Redis。使用服务器队列时，启动 Redis 后执行 `.\start.ps1 -Redis`。AI 功能仍需要配置有效的服务。

首次启动会生成 `backend/.env` 和随机会话密钥，并执行数据库迁移。缺少模型依赖时使用明确标注的演示检测器，**不会识别真实害虫**。AI 默认关闭，不会调用付费接口。

首次克隆安装（Python 3.12 与模型依赖清单一致）：

```powershell
git clone https://github.com/fuyiwei2005-hub/HeCha.git
cd HeCha
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm ci
npm run build
cd ..
.\start.ps1
```

## 启用真实识别和 AI 建议

使用基础依赖对应的虚拟环境安装 `backend/requirements-model.txt`，然后在 `backend/.env` 设置相对于 backend 的权重路径：

```env
MODEL_PATH=../model_weights/best.pt
ALLOW_MOCK_DETECTOR=false
```

本仓库包含 `model_weights/best.pt`（约 10 MB）。权重依赖 `backend/ultralytics` 中的定制实现，不能直接替换为官方同名包。此轮重构保留权重和检测参数；运行环境的迁移与模型精度需要用真实图集另行验收。

配置 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` 后启用建议。`DEEPSEEK_THINKING_PARAM` 是厂商参数，需与所选服务匹配；填空则不发送。API 和两个 Worker 必须使用同一份环境配置及数据库。

## 工程结构

```text
backend/app/api/                 HTTP 鉴权、参数与响应
backend/app/services/image_detection.py   图片业务流程
backend/app/services/admission.py         解码前的并发、排队和取消控制
backend/app/services/analysis_jobs.py     持久化建议任务、配额与结果回写
backend/app/services/task_maintenance.py  后台超时巡检与可靠派发
backend/app/workers/video.py              视频处理与心跳
backend/app/workers/analysis.py           独立建议队列
backend/alembic/versions/0009_async_analysis.py  新增状态字段及历史数据兼容
frontend/src/components/         上传、结果、建议状态、视频时间线等
frontend/src/hooks/useTaskPolling.ts       图片建议和视频任务轮询
```

模型的 `confidence` 保持原始视觉分数；`ranking_score` 只用于作物先验排序。历史加权记录通过响应归一化兼容，不改写原记录。视频次数为跨帧检出次数，不能解释成独立虫体数。

## 数据迁移与任务语义

`0009_async_analysis` 给历史有建议的记录标记 `completed`，其余历史记录标记 `disabled`，避免自动触发付费调用。

API 先把任务与文件关系提交到数据库，再由巡检派发到 Redis。Redis 恢复后可继续派发；超过排队期限的任务会明确失败。处理中的任务通过心跳和尝试编号保护，过期或删除后，旧 Worker 不能覆盖新状态。

GET 查询不再修改任务状态。重试建议使用 `POST /api/detections/{id}/analysis`；其他接口保持现有路径。新增响应字段 `analysis_status` 和 `analysis_error`。

迁移前备份原数据库。需要回退时先恢复相匹配的代码及数据库备份；不要让旧代码与新任务 Worker 混跑。

## Docker

复制根目录 `.env.example` 并配置随机 `SECRET_KEY`、`POSTGRES_PASSWORD`。真实模型部署设置 `INSTALL_YOLO=true` 和 `MODEL_PATH=/models/best.pt`，模型目录挂载到 `/models`。

```powershell
docker compose up --build
```

默认启动 API、视频 Worker、建议 Worker、PostgreSQL 和 Redis。API 镜像构建同一份 React 页面，入口 `http://localhost:8000/`。Redis 使用 `noeviction`，避免任务数据被作为缓存淘汰。

本轮已验证 Compose 配置，当前机器 Docker 引擎未运行，尚未执行镜像构建与容器部署。

## 验证

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
cd ..
.\.venv\Scripts\python.exe tools\check_migrations.py
```

浏览器集成测试使用 `tools/smoke_app.py` 的隔离数据库和模拟检测器、模拟 AI，检查注册登录、图片结果、建议失败与重试、参考资料、聊天反馈、视频时间线、移动布局、清空和退出。运行 `tools/browser_smoke.cjs` 需要 Playwright 和 Edge；可用 `PESTGUARD_PLAYWRIGHT_MODULE` 指定 Playwright 模块路径。

测试记录及截图在 `output/`。工程重构的验证不代表识别准确率提高，也不代表真实 AI 服务已经验证。

旧参赛资料和审计报告保留在 `docs/`，用于追溯；当前启动与架构以本 README 为准。

## 源码与隐私

仓库不包含 API 密钥、服务器登录信息、实际 `.env`、用户数据库、上传记录、虚拟环境、`node_modules` 或构建产物。请参考 `.env.example` 自行配置服务；不要将实际环境文件提交到 Git。

前端需要先执行 `npm ci && npm run build`。模型功能需要额外安装 `backend/requirements-model.txt`；仅安装基础依赖时，启动器会明确标注演示模式。

藤蔓交互专项验证：`tools/browser_vine.cjs`，覆盖逐片展开、滚动回退、六个功能入口、键盘操作和手机布局。可通过 `PESTGUARD_PYTHON` 指定测试用 Python，通过 `PESTGUARD_PLAYWRIGHT_MODULE` 指定 Playwright。

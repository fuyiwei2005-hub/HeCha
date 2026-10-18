import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api import auth, detections, statistics, videos
from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.core.redis_guard import close as redis_close
from app.core.schema_check import report_schema_health
from app.models.user import User
from app.services.detector import detector
from app.services.knowledge import get_knowledge_base
from app.services.llm import llm
from app.services.task_maintenance import maintenance_loop
from app.services.queue import close_pool


logger = logging.getLogger(__name__)
settings = get_settings()


def _warm_knowledge() -> float:
    """启动期建好 BM25 索引。知识库缺失/损坏时只告警，绝不能拖垮启动。"""
    started = time.perf_counter()
    try:
        kb = get_knowledge_base()
        kb.load()
        if not kb.available:
            logger.warning("知识库不可用，RAG 将退化为纯模型作答：%s", kb.error)
    except Exception:  # noqa: BLE001
        logger.exception("知识库预热失败，RAG 将退化为纯模型作答")
    return time.perf_counter() - started
BACKEND_ROOT = Path(__file__).resolve().parent.parent          # backend/
# Vite 构建产物（React 版）。
FRONTEND_DIST = BACKEND_ROOT.parent / "frontend" / "dist"
DIST_INDEX = FRONTEND_DIST / "index.html"

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not (BACKEND_ROOT / "static/index.html").is_file():
        logger.warning("前端尚未构建：请在 frontend 目录执行 npm ci 和 npm run build")
    # 先查表结构：缺列时下面所有查询都会抛 500，得先把话说在前面的日志里。
    # 不抛异常中断启动 —— 服务活着，用户至少还能看到登录页并知道自己该做什么。
    await report_schema_health(engine)
    # 兼容老账号：没有 username 的用邮箱 @ 前面那段补上，保证新登录页能用账号登录
    async with SessionLocal() as db:
        try:
            rows = await db.scalars(select(User).where(User.username.is_(None)))
            for u in rows.all():
                base = (u.email or f"user{u.id}").split("@")[0][:32] or f"user{u.id}"
                candidate, n = base, 1
                while await db.scalar(select(User).where(User.username == candidate)):
                    n += 1
                    candidate = f"{base}{n}"
                u.username = candidate
            # 一次提交：逐行 commit 时，中间任何一行撞上唯一约束都会抛异常，
            # 而这里是启动路径 —— 一抛异常整个服务就起不来，
            # 为了几个历史账号把线上搞挂不值得。
            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()
            logger.exception("回填历史账号 username 失败，跳过（不影响服务启动）")

    # 预热 YOLO：把「第一次请求等好几秒」挪到启动阶段。
    # 演示时评委的第一个动作就是上传，这一步必须提前付掉。
    elapsed = await asyncio.to_thread(detector.warmup)
    if elapsed:
        logger.info("detector warmed up in %.2fs", elapsed)
    elif settings.model_path:
        # 配了模型却预热失败 —— 这是"服务活着但干不了活"，必须显眼。
        # 以前这里静默（只有 detector.warmup 内部一行 print），
        # 于是 /api/health 仍返回 status=ok，健康检查照过。
        logger.error(
            "detector 预热未完成（MODEL_PATH=%s）。"
            "检测接口首次调用会现场加载模型，若持续失败请检查权重文件与依赖。",
            settings.model_path,
        )

    # 预热 RAG 知识库：首次检索要读 JSON + 分词建 BM25 索引（几百毫秒），
    # 和模型同理，不能让第一个上传的用户替我们付这笔账。
    kb_elapsed = await asyncio.to_thread(_warm_knowledge)
    logger.info("knowledge base ready in %.2fs", kb_elapsed)

    maintenance = asyncio.create_task(maintenance_loop())
    try:
        yield
    finally:
        maintenance.cancel()
        with suppress(asyncio.CancelledError):
            await maintenance
    # 关闭视频任务的 ARQ 连接池
    await close_pool()
    await redis_close()
    await engine.dispose()


# Swagger 文档的接口分组说明（评委/评审常会直接翻阅 /docs）
tags_metadata = [
    {"name": "auth", "description": "注册、登录与当前登录用户查询。JWT 无状态鉴权。"},
    {
        "name": "detections",
        "description": "图片识别完成后立即保存并返回，AI 建议由独立任务生成。"
        "支持查询记录、通过鉴权或短时票据下载结果、重试建议、删除记录。",
    },
    {
        "name": "videos",
        "description": "视频任务：提交后由本地任务执行器或 Redis/ARQ Worker 抽帧处理，"
        "支持轮询进度、查询结果与失败状态。",
    },
    {
        "name": "statistics",
        "description": "当前用户的检测统计与虫种分布。所有数据按用户严格隔离。",
    },
]

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="禾察 · 农作物害虫智能识别与植保决策 API。"
    "视觉模型定位虫体，识别结果与 AI 建议独立完成；视频异步处理。",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
)
# CORS：Starlette 在 allow_origins 含 "*" 且 allow_credentials=True 时会
# 直接把请求里的 Origin 原样反射回去 —— 任何站点都能带着用户的 Cookie/凭证
# 跨域读接口，等于把同源策略关掉。这里显式拒绝这个组合。
_raw_origins = settings.allowed_origins
_allow_credentials = "*" not in _raw_origins
_allowed_origins = [origin for origin in _raw_origins if origin != "*"]
if not _allow_credentials:
    logger.warning(
        "CORS_ORIGINS 配置了通配符 *，已自动关闭 allow_credentials 以避免凭证跨域泄露；"
        "生产环境请填写具体的前端域名"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth.router, prefix="/api")
app.include_router(detections.router, prefix="/api")
app.include_router(videos.router, prefix="/api")
app.include_router(statistics.router, prefix="/api")


from app.api.health import router as health_router
app.include_router(health_router, prefix="/api")


# Each module has a directly addressable page; API and assets remain unchanged.
from app.api.pages import router as pages_router
app.include_router(pages_router)
app.mount("/static/product", StaticFiles(directory=str(BACKEND_ROOT / "static/product")), name="product-assets")

if DIST_INDEX.is_file():
    # Vite assets use /assets absolute URLs.
    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
    app.mount("/experimental", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="experimental")

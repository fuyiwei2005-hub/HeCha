"""Reconcile tasks in the background, never as a side effect of GET."""
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import and_, or_, update, func, select
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.detection import Detection
from app.services.analysis_jobs import dispatch_pending_analysis, utcnow
from app.services.queue import get_pool

logger = logging.getLogger(__name__)


async def reconcile_tasks():
    settings = get_settings()
    now = utcnow()
    queued_cutoff = now - timedelta(minutes=settings.video_job_timeout_minutes)
    heartbeat_cutoff = now - timedelta(seconds=settings.job_heartbeat_timeout_seconds)
    analysis_cutoff = now - timedelta(seconds=settings.analysis_job_timeout_seconds + 15)
    async with SessionLocal() as db:
        # All predicates are evaluated in the UPDATE itself, fencing concurrent
        # heartbeats and completions rather than overwriting a stale ORM snapshot.
        await db.execute(update(Detection).where(
            Detection.media_type == "video",
            or_(and_(Detection.status == "queued", func.coalesce(Detection.heartbeat_at, Detection.created_at) < queued_cutoff),
                and_(Detection.status == "processing", Detection.heartbeat_at < heartbeat_cutoff),
                and_(Detection.status == "processing", Detection.heartbeat_at.is_(None),
                     Detection.created_at < now - timedelta(minutes=15))),
        ).values(status="failed", error="视频任务超时，请重新提交", job_attempt=None))
        await db.execute(update(Detection).where(or_(
            and_(Detection.analysis_status == "queued", Detection.analysis_requested_at < queued_cutoff),
            and_(Detection.analysis_status == "processing", Detection.analysis_started_at < analysis_cutoff),
        )).values(analysis_status="failed", analysis_error="建议生成超时，可稍后重试"))
        await db.commit()


async def maintenance_loop():
    if get_settings().task_backend == "local":
        from app.services.local_tasks import local_loop
        await local_loop()
        return
    while True:
        try:
            await reconcile_tasks()
            async with asyncio.timeout(3):
                await dispatch_pending_videos()
                await dispatch_pending_analysis()
        except Exception:
            logger.warning("任务巡检或派发暂不可用，将自动重试", exc_info=True)
        await asyncio.sleep(get_settings().maintenance_interval_seconds)


async def dispatch_pending_videos():
    async with SessionLocal() as db:
        rows = (await db.execute(select(Detection.id, Detection.stored_name).where(
            Detection.media_type == "video", Detection.status == "queued",
        ).order_by(Detection.created_at).limit(100))).all()
    if not rows:
        return
    redis = await get_pool()
    for detection_id, stored_name in rows:
        source = get_settings().upload_dir / stored_name
        await redis.enqueue_job("process_video", detection_id, str(source), _job_id=detection_id)

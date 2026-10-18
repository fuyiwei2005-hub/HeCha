"""Persist advice requests before dispatch; Redis is transport, not the source of truth."""
import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.rate_limit import check_llm_quota
from app.models.detection import Detection
from app.services.host_prior import host_prior
from app.services.llm import llm
from app.services.queue import get_pool
from app.services.predictions import normalize_predictions

logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


def analysis_request(predictions):
    if not predictions:
        return {"analysis_status": "skipped", "analysis_error": None}
    if not llm.enabled:
        return {"analysis_status": "disabled", "analysis_error": None}
    return {
        "analysis_status": "queued", "analysis_error": None,
        "analysis_attempt": str(uuid4()), "analysis_requested_at": utcnow(),
        "analysis_started_at": None,
    }


async def dispatch_pending_analysis():
    async with SessionLocal() as db:
        rows = (await db.execute(select(Detection.id, Detection.analysis_attempt).where(
            Detection.analysis_status == "queued", Detection.status == "completed",
        ).order_by(Detection.analysis_requested_at).limit(100))).all()
    if not rows:
        return
    # Bounded externally by maintenance. Requests never wait for Redis or the LLM.
    redis = await get_pool()
    for detection_id, attempt in rows:
        await redis.enqueue_job("process_analysis", detection_id, attempt,
                                _job_id=f"analysis:{detection_id}:{attempt}",
                                _queue_name=get_settings().analysis_queue_name)


async def process_analysis(ctx, detection_id: str, attempt: str):
    async with SessionLocal() as db:
        claimed = await db.execute(update(Detection).where(
            Detection.id == detection_id, Detection.status == "completed",
            Detection.analysis_status == "queued", Detection.analysis_attempt == attempt,
        ).values(analysis_status="processing", analysis_started_at=utcnow()))
        await db.commit()
        if not claimed.rowcount:
            return
        item = await db.get(Detection, detection_id)
        if item is None:
            return
        predictions = normalize_predictions(item.predictions, item.media_type)
        media_type, crop, user_id = item.media_type, item.crop, item.user_id

    text, refs, error = None, [], None
    try:
        # Charge advice only, immediately before calling its provider.
        await check_llm_quota(user_id)
        async with asyncio.timeout(get_settings().analysis_job_timeout_seconds):
            text, refs = await llm.analyze(predictions, media_type,
                                          crop_hint=host_prior.hint_for_llm(crop, predictions) if crop else None)
        if not text:
            error = "建议生成失败，可稍后重试"
    except HTTPException as exc:
        error = "AI 使用次数已达上限，请稍后重试" if exc.status_code == 429 else "AI 服务暂不可用"
    except (Exception, asyncio.CancelledError) as exc:
        error = "建议生成中断，可稍后重试"
        logger.warning("analysis %s failed: %s", detection_id, type(exc).__name__)
        if isinstance(exc, asyncio.CancelledError):
            await finish_analysis(detection_id, attempt, None, [], error)
            raise
    await finish_analysis(detection_id, attempt, text, refs, error)


async def finish_analysis(detection_id, attempt, text, refs, error):
    async with SessionLocal() as db:
        await db.execute(update(Detection).where(
            Detection.id == detection_id, Detection.analysis_attempt == attempt,
            Detection.analysis_status == "processing",
        ).values(analysis_status="completed" if text else "failed", analysis=text,
                 references=refs or None, analysis_error=error))
        await db.commit()

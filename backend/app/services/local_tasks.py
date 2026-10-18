"""Single-process desktop runner; durable database records remain the task source."""
import asyncio
import logging
from sqlalchemy import select
from arq import Retry
from app.core.database import SessionLocal
from app.core.config import get_settings
from app.models.detection import Detection
from app.services.analysis_jobs import process_analysis
from app.workers.video import process_video
logger = logging.getLogger(__name__)

async def _video(did, source):
    for attempt in (1, 2):
        try:
            await process_video({'job_try': attempt}, did, source)
            return
        except Retry:
            await asyncio.sleep(5)

async def local_loop():
    from app.services.task_maintenance import reconcile_tasks
    active = {}
    try:
        while True:
            try:
                for key, task in list(active.items()):
                    if task.done():
                        del active[key]
                        try: task.result()
                        except Exception: logger.exception('Local task failed: %s', key)
                await reconcile_tasks()
                async with SessionLocal() as db:
                    videos = (await db.execute(select(Detection.id, Detection.stored_name).where(
                        Detection.media_type == 'video', Detection.status == 'queued').order_by(Detection.created_at).limit(2))).all()
                    advice = (await db.execute(select(Detection.id, Detection.analysis_attempt).where(
                        Detection.status == 'completed', Detection.analysis_status == 'queued').limit(4))).all()
                if not any(k[0] == 'video' for k in active):
                    for did, name in videos:
                        key = ('video', did)
                        active[key] = asyncio.create_task(_video(did, str(get_settings().upload_dir / name)))
                        break
                for did, attempt in advice:
                    key = ('advice', did)
                    if key not in active and sum(k[0] == 'advice' for k in active) < 2:
                        active[key] = asyncio.create_task(process_analysis({}, did, attempt))
            except Exception:
                logger.warning('Local task scan temporarily unavailable; retrying', exc_info=True)
            await asyncio.sleep(1)
    finally:
        for task in active.values(): task.cancel()
        await asyncio.gather(*active.values(), return_exceptions=True)

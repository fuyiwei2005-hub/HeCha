from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.detection_response import serialize
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import current_user
from app.models.detection import Detection
from app.models.user import User
from app.schemas.detection import DetectionResponse
from app.services.files import save_video
from app.services.analysis_jobs import utcnow


router = APIRouter(prefix="/videos", tags=["videos"])
settings = get_settings()

@router.post("", response_model=DetectionResponse, status_code=202)
async def submit_video(
    file: UploadFile = File(...),
    observation: str | None = Form(None),
    crop: str | None = Form(None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.observation import parse_observation
    from app.services.host_prior import host_prior
    context = parse_observation(observation)
    crop = host_prior.resolve_crop(crop.strip()) if crop and crop.strip() else None
    path, stored_name = await save_video(file, settings.upload_dir, settings.max_video_bytes)
    item = Detection(
        id=str(uuid4()), user_id=user.id, media_type="video",
        original_name=(file.filename or "video")[:255], stored_name=stored_name,
        status="queued", predictions=[], created_at=utcnow(), observation=context, crop=crop,
    )
    db.add(item)
    try:
        await db.commit()
    except BaseException:
        await db.rollback()
        path.unlink(missing_ok=True)
        raise
    await db.refresh(item)
    # The database is the durable outbox. Maintenance dispatches after commit
    # and retries transport failures without losing the user's source video.
    return serialize(item)


@router.get("/{detection_id}", response_model=DetectionResponse)
async def video_status(
    detection_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    # Read-only: timeouts are reconciled by background maintenance.
    item = await db.scalar(
        select(Detection).where(
            Detection.id == detection_id,
            Detection.user_id == user.id,
            Detection.media_type == "video",
        )
    )
    if not item:
        raise HTTPException(404, "Video task not found")
    return serialize(item)



@router.post('/{detection_id}/retry', response_model=DetectionResponse, status_code=202)
async def retry_video(detection_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    item = await db.scalar(select(Detection).where(Detection.id == detection_id,
        Detection.user_id == user.id, Detection.media_type == 'video'))
    if item is None:
        raise HTTPException(404, 'Video task not found')
    if item.status != 'failed':
        return serialize(item)
    source = settings.upload_dir / item.stored_name
    if not source.is_file():
        raise HTTPException(409, '原视频文件已不存在，请重新上传')
    await db.execute(update(Detection).where(Detection.id == detection_id,
        Detection.user_id == user.id, Detection.status == 'failed'
    ).values(status='queued', error=None, job_attempt=None, heartbeat_at=utcnow(),
             video_meta={'progress': {'stage': 'queued'}}, analysis_status='disabled', analysis_error=None))
    await db.commit()
    await db.refresh(item)
    return serialize(item)

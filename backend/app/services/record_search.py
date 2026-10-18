"""User-scoped filtering shared by the paginated record API."""
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.detection import Detection
from app.schemas.detection import DetectionPage
from app.services.detection_response import serialize

async def search_records(db: AsyncSession, user_id: int, offset: int, limit: int,
                         media_type: str | None, status: str | None, q: str | None,
                         start_at: datetime | None, end_at: datetime | None):
    if media_type and media_type not in {'image', 'video'}:
        raise HTTPException(422, '记录类型无效')
    if status and status not in {'queued', 'processing', 'completed', 'failed'}:
        raise HTTPException(422, '任务状态无效')
    def utc(value):
        if value is None: return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    start_at, end_at = utc(start_at), utc(end_at)
    if start_at and end_at and start_at >= end_at:
        raise HTTPException(422, '结束时间必须晚于开始时间')
    filters = [Detection.user_id == user_id]
    if media_type: filters.append(Detection.media_type == media_type)
    if status: filters.append(Detection.status == status)
    if start_at: filters.append(Detection.created_at >= start_at)
    if end_at: filters.append(Detection.created_at < end_at)
    if q and (keyword := q.strip()):
        # SQLAlchemy's JSON serializer can encode Chinese as unicode escapes.
        # Support both representations while treating SQL wildcard characters literally.
        encoded = json.dumps(keyword, ensure_ascii=True)[1:-1]
        predictions = cast(Detection.predictions, String)
        filters.append(or_(Detection.original_name.icontains(keyword, autoescape=True),
                           Detection.crop.icontains(keyword, autoescape=True),
                           predictions.icontains(keyword, autoescape=True),
                           predictions.icontains(encoded, autoescape=True)))
    total = await db.scalar(select(func.count()).select_from(Detection).where(*filters))
    rows = await db.scalars(select(Detection).where(*filters)
                            .order_by(Detection.created_at.desc(), Detection.id.desc())
                            .offset(offset).limit(limit))
    return DetectionPage(items=[serialize(row) for row in rows], total=total or 0,
                         offset=offset, limit=limit)

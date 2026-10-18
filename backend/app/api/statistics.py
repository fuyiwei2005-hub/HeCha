from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import current_user
from app.models.detection import Detection
from app.models.user import User
from app.schemas.statistics import ClassCount, StatisticsResponse
from app.services.pest_names import to_chinese


router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("", response_model=StatisticsResponse)
async def statistics(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    base = Detection.user_id == user.id

    # ① 一次 GROUP BY media_type → 总数 / 图片数 / 视频数
    mt_rows = await db.execute(
        select(Detection.media_type, func.count()).where(base).group_by(Detection.media_type)
    )
    mt = {m: c for m, c in mt_rows.all()}
    total_jobs = sum(mt.values())
    image_jobs = mt.get("image", 0)
    video_jobs = mt.get("video", 0)

    # ② 一次 GROUP BY status → 完成 / 失败
    st_rows = await db.execute(
        select(Detection.status, func.count()).where(base).group_by(Detection.status)
    )
    st = {s: c for s, c in st_rows.all()}
    completed_jobs = st.get("completed", 0)
    failed_jobs = st.get("failed", 0)

    # ③ 只拉 media_type + predictions 两列做虫种聚合
    rows = await db.execute(
        select(Detection.media_type, Detection.predictions).where(base)
    )
    counts: Counter[str] = Counter()
    for media_type, predictions in rows.all():
        if media_type == "image":
            detections = predictions or []
        else:
            detections = [
                p
                for event in (predictions or [])
                for p in (event.get("detections", []) if isinstance(event, dict) else [])
            ]
        counts.update(str(item.get("class", "unknown")) for item in detections)

    return StatisticsResponse(
        total_jobs=total_jobs,
        image_jobs=image_jobs,
        video_jobs=video_jobs,
        completed_jobs=completed_jobs,
        failed_jobs=failed_jobs,
        total_objects=sum(counts.values()),
        classes=[ClassCount(name=name, name_cn=to_chinese(name), count=count)
                 for name, count in counts.most_common()],
    )

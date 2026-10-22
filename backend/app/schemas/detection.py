from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class VideoProgress(BaseModel):
    stage: str
    processed_frames: int = 0
    total_frames: int = 0
    percent: int | None = None
    can_retry: bool = False


class DetectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    media_type: str
    original_name: str
    status: str
    predictions: list[dict[str, Any]]
    # 本次检测使用的作物上下文（寄主先验输入）；None 表示用户未指定
    crop: str | None = None
    # 视频专用：fps / 时长 / 采样帧数 / 是否已转 H.264，前端据此提示完整性
    video_meta: dict[str, Any] | None = None
    progress: VideoProgress | None = None
    result_url: str | None = None
    analysis: str | None = None
    analysis_status: str = "disabled"
    analysis_error: str | None = None
    # RAG 引用溯源列表：[{ref, id, title, body, source}, ...]
    references: list[dict[str, Any]] | None = None
    observation: dict[str, Any] | None = None
    quality: dict[str, Any] | None = None
    feedback_note: str | None = None
    feedback: str | None = None
    error: str | None = None
    created_at: datetime


class DetectionPage(BaseModel):
    items: list[DetectionResponse]
    total: int
    offset: int
    limit: int

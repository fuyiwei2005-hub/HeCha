from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    media_type: Mapped[str] = mapped_column(String(16), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="completed", index=True)
    predictions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # 用户拍摄时告知的作物（寄主先验的输入）。nullable：
    # 老记录与未填作物的检测取值为 None，链路自动走「无先验」分支，不做任何重排。
    crop: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # 视频专用：抽帧统计与转码结果（fps/时长/采样帧数/是否 H.264）
    # 让前端能判断「结果是否完整」，而不是只看到一个目标数
    video_meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_status: Mapped[str] = mapped_column(String(24), default="disabled", server_default="disabled", index=True)
    analysis_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    analysis_attempt: Mapped[str | None] = mapped_column(String(36), nullable=True)
    analysis_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job_attempt: Mapped[str | None] = mapped_column(String(36), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # RAG 引用溯源：生成分析时实际注入的参考资料（编号/标题/来源/正文）
    # 有了它，界面上的 [1][2] 角标才能点开看到原文出处
    references: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    feedback: Mapped[str | None] = mapped_column(String(16), nullable=True)  # good / bad
    feedback_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user = relationship("User", back_populates="detections")

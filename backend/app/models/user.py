from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 注册账号：允许任意字母/数字/下划线组合，不再强制邮箱格式。
    # 保留 email 列（nullable）兼容历史数据与"可选填邮箱"的后续扩展。
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    detections = relationship("Detection", back_populates="user", cascade="all, delete-orphan")


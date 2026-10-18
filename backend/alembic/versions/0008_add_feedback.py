"""add user feedback to detections

Revision ID: 0008_add_feedback
Revises: 0007_add_crop
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_add_feedback"
down_revision = "0007_add_crop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 用户反馈：对一次检测结果点「有用/没用」，用于评估模型与建议质量。
    # 模型里已声明这两个字段（app/models/detection.py），但此前漏了迁移脚本，
    # 导致新环境部署后 SELECT 完整 Detection 实体时报 no such column。
    # 均 nullable —— 历史检测记录不受影响，未反馈就是 None。
    op.add_column("detections", sa.Column("feedback", sa.String(16), nullable=True))
    op.add_column("detections", sa.Column("feedback_note", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("detections", "feedback_note")
    op.drop_column("detections", "feedback")

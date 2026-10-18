"""add video_meta to detections

Revision ID: 0005_add_video_meta
Revises: 0004_add_username_to_users
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_add_video_meta"
down_revision = "0004_add_username_to_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 记录视频抽帧统计与转码结果，让前端能判断「结果是否完整」，
    # 而不只是显示一个目标数量。nullable，老记录不受影响。
    op.add_column("detections", sa.Column("video_meta", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("detections", "video_meta")

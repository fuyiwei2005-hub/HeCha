"""add crop context to detections

Revision ID: 0007_add_crop
Revises: 0006_add_references
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_add_crop"
down_revision = "0006_add_references"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 寄主先验：记录用户拍摄时告知的作物。nullable —— 老记录与不填作物的检测照常工作，
    # 取不到就是 None，链路走「无先验」分支，不做任何重排。
    op.add_column("detections", sa.Column("crop", sa.String(32), nullable=True))
    op.create_index("ix_detections_crop", "detections", ["crop"])


def downgrade() -> None:
    op.drop_index("ix_detections_crop", table_name="detections")
    op.drop_column("detections", "crop")

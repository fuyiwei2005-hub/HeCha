"""add references to detections

Revision ID: 0006_add_references
Revises: 0005_add_video_meta
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_add_references"
down_revision = "0005_add_video_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # RAG 引用溯源：存生成分析时实际注入的参考资料（编号/标题/来源/正文），
    # 这样界面上的 [1][2] 角标才能点开核对原文出处。nullable，老记录不受影响。
    op.add_column("detections", sa.Column("references", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("detections", "references")

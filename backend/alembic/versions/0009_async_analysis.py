"""Separate detection completion from advice and fence worker attempts."""
from alembic import op
import sqlalchemy as sa

revision = "0009_async_analysis"
down_revision = "0008_add_feedback"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("detections", sa.Column("analysis_status", sa.String(24), nullable=False, server_default="disabled"))
    for name, kind in [
        ("analysis_error", sa.String(500)), ("analysis_attempt", sa.String(36)),
        ("analysis_requested_at", sa.DateTime(timezone=True)),
        ("analysis_started_at", sa.DateTime(timezone=True)),
        ("job_attempt", sa.String(36)), ("heartbeat_at", sa.DateTime(timezone=True)),
    ]:
        op.add_column("detections", sa.Column(name, kind, nullable=True))
    op.create_index("ix_detections_analysis_status", "detections", ["analysis_status"])
    op.execute("UPDATE detections SET analysis_status = 'completed' WHERE analysis IS NOT NULL AND analysis <> ''")


def downgrade():
    op.drop_index("ix_detections_analysis_status", table_name="detections")
    for name in ["heartbeat_at", "job_attempt", "analysis_started_at", "analysis_requested_at",
                 "analysis_attempt", "analysis_error", "analysis_status"]:
        op.drop_column("detections", name)

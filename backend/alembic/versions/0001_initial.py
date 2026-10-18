"""Create users and detections tables."""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "detections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("predictions", sa.JSON(), nullable=False),
        sa.Column("result_path", sa.String(255), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_detections_user_id", "detections", ["user_id"])
    op.create_index("ix_detections_media_type", "detections", ["media_type"])
    op.create_index("ix_detections_status", "detections", ["status"])
    op.create_index("ix_detections_created_at", "detections", ["created_at"])


def downgrade() -> None:
    op.drop_table("detections")
    op.drop_table("users")

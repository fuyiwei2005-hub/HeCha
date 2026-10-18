"""Create chat_messages table for multi-turn AI follow-up questions."""
from alembic import op
import sqlalchemy as sa


revision = "0003_create_chat_messages"
down_revision = "0002_add_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("detection_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["detection_id"], ["detections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_detection_id", "chat_messages", ["detection_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_detection_id", table_name="chat_messages")
    op.drop_table("chat_messages")

"""add username to users

Revision ID: 0004_add_username_to_users
Revises: 0003_create_chat_messages
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_add_username_to_users"
down_revision = "0003_create_chat_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # nullable=True 让已有的账号（demo@example.com 等）不受影响；
    # 应用层保证新注册用户一定有 username。
    op.add_column("users", sa.Column("username", sa.String(64), nullable=True))
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    # SQLite 改列可空性需要 batch_alter_table
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email", existing_type=sa.String(320), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email", existing_type=sa.String(320), nullable=False)
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")

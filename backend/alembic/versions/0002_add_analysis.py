"""Add analysis (DeepSeek LLM interpretation) column to detections."""
from alembic import op
import sqlalchemy as sa


revision = "0002_add_analysis"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("detections", sa.Column("analysis", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("detections", "analysis")

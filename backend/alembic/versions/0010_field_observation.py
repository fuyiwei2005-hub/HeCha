"""Persist field observations and image quality hints."""
from alembic import op
import sqlalchemy as sa
revision='0010_field_observation'
down_revision='0009_async_analysis'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('detections',sa.Column('observation',sa.JSON(),nullable=True))
    op.add_column('detections',sa.Column('quality',sa.JSON(),nullable=True))

def downgrade():
    op.drop_column('detections','quality')
    op.drop_column('detections','observation')

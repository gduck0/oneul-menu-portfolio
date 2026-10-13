"""서비스 스키마 생성."""
from alembic import op
from sqlalchemy.schema import CreateSchema, DropSchema

revision = '0001_app_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(CreateSchema('app'))


def downgrade():
    op.execute(DropSchema('app'))

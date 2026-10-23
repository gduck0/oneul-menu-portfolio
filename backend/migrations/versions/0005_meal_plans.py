from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision='0005_meal_plans'
down_revision='0004_personalization'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('meal_plans',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('owner_key',sa.String(66),nullable=False),sa.Column('client_request_id',sa.String(36),nullable=False),
        sa.Column('input_hash',sa.String(64),nullable=False),sa.Column('plan_date',sa.Date(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('payload',JSONB(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('owner_key','client_request_id',name='uq_meal_plan_request'),
        sa.CheckConstraint('version > 0',name='ck_meal_plan_version'),schema='app')
    op.create_index('ix_app_meal_plans_owner_key','meal_plans',['owner_key'],schema='app')
    op.create_table('plan_operations',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('plan_id',sa.String(36),sa.ForeignKey('app.meal_plans.id'),nullable=False),
        sa.Column('client_request_id',sa.String(36),nullable=False),sa.Column('input_hash',sa.String(64),nullable=False),
        sa.Column('payload',JSONB(),nullable=False),sa.UniqueConstraint('plan_id','client_request_id',name='uq_plan_operation_request'),schema='app')


def downgrade():
    op.drop_table('plan_operations',schema='app')
    op.drop_table('meal_plans',schema='app')

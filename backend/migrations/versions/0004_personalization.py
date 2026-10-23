from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0004_personalization'
down_revision = '0003_accounts_and_records'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('personal_settings', sa.Column('owner_key', sa.String(66), primary_key=True),
                    sa.Column('payload', JSONB(), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False), schema='app')
    op.create_table('meal_entries', sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('owner_key', sa.String(66), nullable=False), sa.Column('client_record_id', sa.String(36), nullable=False),
                    sa.Column('input_hash', sa.String(64), nullable=False), sa.Column('eaten_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('payload', JSONB(), nullable=False), sa.UniqueConstraint('owner_key','client_record_id',name='uq_meal_entry_request'), schema='app')
    op.create_index('ix_app_meal_entries_owner_key', 'meal_entries', ['owner_key'], schema='app')
    op.create_index('ix_app_meal_entries_eaten_at', 'meal_entries', ['eaten_at'], schema='app')
    op.create_table('menu_feedback', sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('owner_key', sa.String(66), nullable=False), sa.Column('context_id', sa.String(36), nullable=False),
                    sa.Column('phase', sa.String(20), nullable=False), sa.Column('food_id', sa.String(64), sa.ForeignKey('app.foods.id')),
                    sa.Column('food_code', sa.String(80)), sa.Column('rating', sa.String(10), nullable=False),
                    sa.Column('reason', sa.String(30)), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
                    sa.UniqueConstraint('owner_key','context_id','phase','food_id',name='uq_menu_feedback_context',postgresql_nulls_not_distinct=True),
                    sa.CheckConstraint("phase IN ('recommendation','consumed')",name='ck_feedback_phase'),
                    sa.CheckConstraint("rating IN ('like','neutral','dislike')",name='ck_feedback_rating'), schema='app')
    op.create_index('ix_app_menu_feedback_owner_key', 'menu_feedback', ['owner_key'], schema='app')


def downgrade():
    for name in ('menu_feedback','meal_entries','personal_settings'):
        op.drop_table(name,schema='app')

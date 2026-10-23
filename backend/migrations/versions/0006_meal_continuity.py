from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0006_meal_continuity'
down_revision = '0005_meal_plans'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('meal_entries', sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False), schema='app')
    op.add_column('meal_entries', sa.Column('cancelled_at', sa.DateTime(timezone=True)), schema='app')
    op.create_table('meal_changes', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_key', sa.String(66), nullable=False), sa.Column('client_request_id', sa.String(36), nullable=False),
        sa.Column('input_hash', sa.String(64), nullable=False), sa.Column('meal_id', sa.String(36), sa.ForeignKey('app.meal_entries.id'), nullable=False),
        sa.Column('action', sa.String(20), nullable=False), sa.Column('before', JSONB(), nullable=False),
        sa.Column('payload', JSONB(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('owner_key', 'client_request_id', name='uq_meal_change_request'), schema='app')
    op.create_index('ix_app_meal_changes_owner_key', 'meal_changes', ['owner_key'], schema='app')
    op.create_table('guest_transfers', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('guest_key', sa.String(66), nullable=False, unique=True), sa.Column('user_key', sa.String(66), nullable=False),
        sa.Column('client_request_id', sa.String(36), nullable=False), sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('payload', JSONB(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('user_key', 'client_request_id', name='uq_guest_transfer_request'), schema='app')


def downgrade():
    op.drop_table('guest_transfers', schema='app')
    op.drop_table('meal_changes', schema='app')
    op.drop_column('meal_entries', 'cancelled_at', schema='app')
    op.drop_column('meal_entries', 'version', schema='app')

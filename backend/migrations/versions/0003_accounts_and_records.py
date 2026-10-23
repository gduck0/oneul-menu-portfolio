"""계정 세션·추천 발급·최종 선택·선택 신체 정보."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0003_accounts_and_records'
down_revision = '0002_food_catalog'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users', sa.Column('id', sa.String(36), primary_key=True), sa.Column('username', sa.String(30), unique=True, nullable=False),
                    sa.Column('password_hash', sa.String(300), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), schema='app')
    op.create_table('auth_sessions', sa.Column('token_hash', sa.String(64), primary_key=True),
                    sa.Column('user_id', sa.String(36), sa.ForeignKey('app.users.id', ondelete='CASCADE'), nullable=False),
                    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False), schema='app')
    op.create_index('ix_app_auth_sessions_user_id', 'auth_sessions', ['user_id'], schema='app')
    op.create_table('recommendation_events', sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('user_id', sa.String(36), sa.ForeignKey('app.users.id')), sa.Column('guest_token_hash', sa.String(64)),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('input_hash', sa.String(64), nullable=False),
                    sa.Column('payload', JSONB(), nullable=False),
                    sa.CheckConstraint('(user_id IS NULL) <> (guest_token_hash IS NULL)', name='ck_recommendation_one_owner'), schema='app')
    op.create_index('ix_app_recommendation_events_user_id', 'recommendation_events', ['user_id'], schema='app')
    op.create_index('ix_app_recommendation_events_created_at', 'recommendation_events', ['created_at'], schema='app')
    op.create_table('meal_choices', sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('user_id', sa.String(36), sa.ForeignKey('app.users.id'), nullable=False), sa.Column('client_record_id', sa.String(36), nullable=False),
                    sa.Column('recommendation_id', sa.String(36), sa.ForeignKey('app.recommendation_events.id'), nullable=False),
                    sa.Column('food_id', sa.String(64), sa.ForeignKey('app.foods.id'), nullable=False), sa.Column('selected_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('input_hash', sa.String(64), nullable=False), sa.Column('nutrition', JSONB(), nullable=False), sa.Column('reason', sa.String(150), nullable=False),
                    sa.UniqueConstraint('user_id', 'client_record_id', name='uq_choice_client_record'),
                    sa.UniqueConstraint('user_id', 'recommendation_id', name='uq_choice_recommendation'), schema='app')
    op.create_index('ix_app_meal_choices_user_id', 'meal_choices', ['user_id'], schema='app')
    op.create_index('ix_app_meal_choices_selected_at', 'meal_choices', ['selected_at'], schema='app')
    op.create_table('user_profiles', sa.Column('user_id', sa.String(36), sa.ForeignKey('app.users.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('height_cm', sa.Numeric(5, 2)), sa.Column('weight_kg', sa.Numeric(6, 2)),
                    sa.CheckConstraint('(height_cm IS NULL) = (weight_kg IS NULL)', name='ck_profile_complete_pair'),
                    sa.CheckConstraint('height_cm IS NULL OR height_cm BETWEEN 100 AND 250', name='ck_profile_height'),
                    sa.CheckConstraint('weight_kg IS NULL OR weight_kg BETWEEN 20 AND 300', name='ck_profile_weight'), schema='app')


def downgrade():
    for table in ('user_profiles', 'meal_choices', 'recommendation_events', 'auth_sessions', 'users'):
        op.drop_table(table, schema='app')

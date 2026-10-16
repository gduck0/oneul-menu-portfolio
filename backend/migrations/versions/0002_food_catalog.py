"""출처 스냅샷과 음식 영양 자료."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0002_food_catalog'
down_revision = '0001_app_schema'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('nutrition_snapshots',
                    sa.Column('id', sa.String(64), primary_key=True), sa.Column('source_url', sa.Text(), nullable=False),
                    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False), sa.Column('row_count', sa.Integer(), nullable=False),
                    sa.Column('active', sa.Boolean(), nullable=False), sa.Column('manifest', JSONB(), nullable=False), schema='app')
    op.create_index('uq_active_nutrition_snapshot', 'nutrition_snapshots', ['active'], unique=True, schema='app', postgresql_where=sa.text('active = true'))
    op.create_table('foods',
                    sa.Column('id', sa.String(64), primary_key=True),
                    sa.Column('snapshot_id', sa.String(64), sa.ForeignKey('app.nutrition_snapshots.id'), nullable=False),
                    sa.Column('food_code', sa.String(80), nullable=False), sa.Column('name', sa.String(300), nullable=False),
                    sa.Column('normalized_name', sa.String(300), nullable=False), sa.Column('company', sa.String(300)), sa.Column('category', sa.String(30)),
                    sa.Column('basis_amount', sa.Numeric(14, 5), nullable=False), sa.Column('basis_unit', sa.String(2), nullable=False),
                    *(sa.Column(name, sa.Numeric(14, 5)) for name in ('energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g')),
                    sa.Column('provider', sa.String(300), nullable=False), sa.Column('reference_date', sa.String(10), nullable=False),
                    sa.Column('production_date', sa.String(10)), sa.Column('source_weight', sa.String(100)), sa.Column('raw', JSONB(), nullable=False),
                    sa.UniqueConstraint('snapshot_id', 'food_code', name='uq_food_snapshot_code'),
                    sa.CheckConstraint('basis_amount > 0', name='ck_food_positive_basis'),
                    sa.CheckConstraint("basis_unit IN ('g', 'mL')", name='ck_food_basis_unit'),
                    *(sa.CheckConstraint(f'{name} IS NULL OR {name} >= 0', name='ck_food_' + suffix) for name, suffix in
                      [('energy_kcal', 'energy'), ('protein_g', 'protein'), ('fat_g', 'fat'), ('carbohydrate_g', 'carbohydrate')]),
                    schema='app')
    op.create_index('ix_app_foods_normalized_name', 'foods', ['normalized_name'], schema='app')
    op.create_index('ix_app_foods_category', 'foods', ['category'], schema='app')


def downgrade():
    op.drop_table('foods', schema='app')
    op.drop_table('nutrition_snapshots', schema='app')

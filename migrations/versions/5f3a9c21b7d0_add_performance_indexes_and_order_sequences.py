"""Performance indexes and order sequence counter

Revision ID: 5f3a9c21b7d0
Revises: c0de7f2a5b31
Create Date: 2026-08-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f3a9c21b7d0'
down_revision: Union[str, Sequence[str], None] = 'c0de7f2a5b31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Common buyer-facing listing: active products, newest first.
    op.create_index(
        'ix_products_active_created',
        'products',
        ['in_stock', 'is_deleted', sa.text('created_at DESC')],
        unique=False,
    )
    # Price sorting on the shop page (price-low / price-high).
    op.create_index(
        'ix_products_active_price',
        'products',
        ['in_stock', 'is_deleted', 'price'],
        unique=False,
    )
    # Recent-orders sort on the dashboard.
    op.create_index('ix_orders_created_at', 'orders', ['created_at'], unique=False)
    # Home page hero picks the most recently updated seller.
    op.create_index('ix_sellers_updated_at', 'sellers', ['updated_at'], unique=False)

    # Atomic per-(store_prefix, day) counter backing OrderService.generate_order_id.
    op.create_table(
        'order_sequences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('store_prefix', sa.String(length=10), nullable=False),
        sa.Column('date', sa.String(length=8), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('store_prefix', 'date', name='uq_order_sequences_prefix_date'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('order_sequences')
    op.drop_index('ix_sellers_updated_at', table_name='sellers')
    op.drop_index('ix_orders_created_at', table_name='orders')
    op.drop_index('ix_products_active_price', table_name='products')
    op.drop_index('ix_products_active_created', table_name='products')

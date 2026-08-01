"""Multi-item orders: order_items table, drop legacy single-product columns

Revision ID: c0de7f2a5b31
Revises: f77d2dcc5905
Create Date: 2026-07-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c0de7f2a5b31'
down_revision: Union[str, Sequence[str], None] = 'f77d2dcc5905'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Clear legacy single-product orders (existing data is intentionally dropped)
    op.execute("DELETE FROM order_status_logs")
    op.execute("DELETE FROM orders")

    op.add_column(
        'orders',
        sa.Column('delivery_fee', sa.Numeric(scale=2), nullable=False, server_default='150.00'),
    )

    op.create_table(
        'order_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('product_name', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column('product_price', sa.Numeric(scale=2), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('attributes_selected', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('subtotal', sa.Numeric(scale=2), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)

    op.drop_constraint('orders_product_id_fkey', 'orders', type_='foreignkey')
    op.drop_column('orders', 'product_id')
    op.drop_column('orders', 'product_name')
    op.drop_column('orders', 'product_price')
    op.drop_column('orders', 'quantity')
    op.drop_column('orders', 'attributes_selected')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('orders', sa.Column('attributes_selected', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('orders', sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('orders', sa.Column('product_price', sa.Numeric(scale=2), nullable=False, server_default='0.00'))
    op.add_column('orders', sa.Column('product_name', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False, server_default=''))
    op.add_column('orders', sa.Column('product_id', sa.Integer(), nullable=False, server_default='0'))
    op.create_foreign_key('orders_product_id_fkey', 'orders', 'products', ['product_id'], ['id'])
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_table('order_items')
    op.drop_column('orders', 'delivery_fee')

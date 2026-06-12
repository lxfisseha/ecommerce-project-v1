"""add phone_hash to seller and otp_code

Revision ID: 0ea9e0c080b4
Revises: 722d31ac0edf
Create Date: 2026-06-12 20:54:48.858797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '0ea9e0c080b4'
down_revision: Union[str, Sequence[str], None] = '722d31ac0edf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns as nullable first
    op.add_column('sellers', sa.Column('phone_hash', sa.String(length=256), nullable=True))
    op.add_column('otp_codes', sa.Column('phone_hash', sa.String(length=256), nullable=True))
    op.add_column('orders', sa.Column('buyer_phone_hash', sa.String(length=256), nullable=True))
    op.add_column('orders', sa.Column('delivery_address_hash', sa.String(length=256), nullable=True))

    # 2. Update existing data with placeholders to avoid NOT NULL violation
    # The application will need to handle re-hashing if necessary, 
    # but at least the schema will be correct.
    op.execute("UPDATE sellers SET phone_hash = 'PENDING_HASH_' || id")
    op.execute("UPDATE otp_codes SET phone_hash = 'PENDING_HASH_' || id")
    op.execute("UPDATE orders SET buyer_phone_hash = 'PENDING_HASH_' || id")

    # 3. Set NOT NULL
    op.alter_column('sellers', 'phone_hash', nullable=False)
    op.alter_column('otp_codes', 'phone_hash', nullable=False)
    op.alter_column('orders', 'buyer_phone_hash', nullable=False)

    # 4. Alter phone types
    op.alter_column('sellers', 'phone',
               existing_type=sa.VARCHAR(length=15),
               type_=sa.String(length=512),
               existing_nullable=False)
    op.alter_column('otp_codes', 'phone',
               existing_type=sa.VARCHAR(length=15),
               type_=sa.String(length=512),
               existing_nullable=False)
    op.alter_column('orders', 'buyer_phone',
               existing_type=sa.VARCHAR(length=15),
               type_=sa.String(length=512),
               existing_nullable=False)

    # 5. Handle indices
    # Drop old indices if they exist (based on your autogenerate output)
    try:
        op.drop_index('ix_sellers_phone', table_name='sellers')
    except Exception:
        pass
    try:
        op.drop_index('ix_otp_codes_phone', table_name='otp_codes')
    except Exception:
        pass
    try:
        op.drop_index('ix_orders_buyer_phone', table_name='orders')
    except Exception:
        pass

    op.create_index(op.f('ix_sellers_phone_hash'), 'sellers', ['phone_hash'], unique=True)
    op.create_index(op.f('ix_otp_codes_phone_hash'), 'otp_codes', ['phone_hash'], unique=False)
    op.create_index(op.f('ix_orders_buyer_phone_hash'), 'orders', ['buyer_phone_hash'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_orders_buyer_phone_hash'), table_name='orders')
    op.create_index('ix_orders_buyer_phone', 'orders', ['buyer_phone'], unique=False)
    op.drop_column('orders', 'delivery_address_hash')
    op.drop_column('orders', 'buyer_phone_hash')
    
    op.drop_index(op.f('ix_otp_codes_phone_hash'), table_name='otp_codes')
    op.create_index('ix_otp_codes_phone', 'otp_codes', ['phone'], unique=False)
    op.drop_column('otp_codes', 'phone_hash')
    
    op.drop_index(op.f('ix_sellers_phone_hash'), table_name='sellers')
    op.create_index('ix_sellers_phone', 'sellers', ['phone'], unique=True)
    op.drop_column('sellers', 'phone_hash')
    
    op.alter_column('sellers', 'phone', type_=sa.VARCHAR(length=15))
    op.alter_column('otp_codes', 'phone', type_=sa.VARCHAR(length=15))
    op.alter_column('orders', 'buyer_phone', type_=sa.VARCHAR(length=15))

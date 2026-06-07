"""add_first_and_last_name_to_seller

Revision ID: 722d31ac0edf
Revises: bf9fa547aa63
Create Date: 2026-06-06 22:20:09.725522

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '722d31ac0edf'
down_revision: Union[str, Sequence[str], None] = 'bf9fa547aa63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add columns as nullable first
    op.add_column('sellers', sa.Column('first_name', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True))
    op.add_column('sellers', sa.Column('last_name', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True))
    
    # Fill existing rows with a placeholder
    op.execute("UPDATE sellers SET first_name = 'Placeholder', last_name = 'Seller'")
    
    # Now set them to NOT NULL
    op.alter_column('sellers', 'first_name', nullable=False)
    op.alter_column('sellers', 'last_name', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sellers', 'last_name')
    op.drop_column('sellers', 'first_name')

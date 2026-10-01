"""drop product_images.image_url

Revision ID: d4e8a1c75b92
Revises: b5b9475effb4
Create Date: 2026-10-01 09:40:00.000000

The column held a Cloudinary URL. Storage moved to the local filesystem in
2cd99aa, which writes object_name instead, so the column was never populated
and templates that still read it rendered empty image sources.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e8a1c75b92'
down_revision: Union[str, Sequence[str], None] = 'b5b9475effb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the legacy Cloudinary URL column."""
    op.drop_column('product_images', 'image_url')


def downgrade() -> None:
    """Restore the column as non-null with an empty default."""
    op.add_column(
        'product_images',
        sa.Column('image_url', sa.String(), nullable=False, server_default=''),
    )

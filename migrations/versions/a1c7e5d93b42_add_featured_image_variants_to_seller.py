"""add featured_image_variants to seller

Revision ID: a1c7e5d93b42
Revises: d4e8a1c75b92
Create Date: 2026-10-02 00:00:00.000000

sellers.featured_image is a bare object key rather than a ProductImage row, so
nothing ever generated a variant for it and the homepage banner served the
untouched original: 304 KB on a page with a 50 KB budget for that image. This
column records the generated WebP, shaped like product_images.processed_urls.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a1c7e5d93b42'
down_revision: Union[str, Sequence[str], None] = 'd4e8a1c75b92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sellers', sa.Column('featured_image_variants', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sellers', 'featured_image_variants')

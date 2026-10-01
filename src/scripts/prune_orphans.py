"""
Delete stored image files that no database row references.

Useful after a reset that dropped rows without removing files, or to reclaim
space from failed or deleted products. Reports what it would do; pass
--apply to actually unlink.
"""
import argparse
import asyncio
import logging
import sys

from sqlmodel import select

from src.database import async_session_maker
from src.features.auth.models import Seller, OtpCode  # noqa: F401
from src.features.orders.models import Order, OrderStatusLog  # noqa: F401
from src.features.products.models import (
    Product,
    ProductAttribute,
    ProductImage,
    ProductTagLink,
    Tag,
)
from src.utils.storage import LocalStorage

logger = logging.getLogger(__name__)


async def collect_referenced(session) -> set[str]:
    """
    Every object key the database still points at.

    Takes a session rather than opening one so tests can pass their own. Missing
    a key here is not a no-op: prune deletes the file.
    """
    referenced: set[str] = set()

    # Each result is bound to a variable before reading it. Chaining .scalars()
    # directly onto session.execute() raised "ChunkedIteratorResult has no
    # attribute 'scalars'" in this script even though the identical chained form
    # worked outside it.
    image_result = await session.execute(select(ProductImage))
    for image in image_result.scalars().all():
        if image.object_name:
            referenced.add(image.object_name)
        for key in (image.processed_urls or {}).values():
            referenced.add(key)

    seller_result = await session.execute(select(Seller))
    for seller in seller_result.scalars().all():
        if seller.featured_image:
            referenced.add(seller.featured_image)
        # Banner variants live under processed/sellers and are not product
        # images, so they are tracked here rather than by the ProductImage loop
        # above. Without this the generated banner reads as an orphan and is
        # deleted on the next prune.
        for key in (seller.featured_image_variants or {}).values():
            referenced.add(key)

    return referenced


async def collect_orphans() -> tuple[list[str], int]:
    storage = LocalStorage()
    root = storage.base_path

    async with async_session_maker() as session:
        referenced = await collect_referenced(session)

    on_disk = {
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
    }
    orphans = sorted(on_disk - referenced)
    total = sum((root / key).stat().st_size for key in orphans)
    return orphans, total


async def prune(apply: bool) -> int:
    orphans, total = await collect_orphans()

    print(f"orphaned files: {len(orphans)}  ({total / 1024:.0f} KB)")
    for key in orphans[:10]:
        print("   ", key)
    if len(orphans) > 10:
        print(f"    ... and {len(orphans) - 10} more")

    if not orphans:
        return 0
    if not apply:
        print("\nDry run. Re-run with --apply to delete them.")
        return 0

    storage = LocalStorage()
    removed = 0
    for key in orphans:
        if storage.delete(key):
            removed += 1
    print(f"\nRemoved {removed} file(s), reclaiming {total / 1024:.0f} KB.")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete the files (default is a dry run)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(prune(args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())

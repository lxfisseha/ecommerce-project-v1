"""
Re-run variant generation for images that already exist.

Needed after changing SIZES, the output quality, or the upscale rule, since
processed_urls and the files on disk are only written once at upload time.
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

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
from src.scripts.process_images import enqueue_image_processing

logger = logging.getLogger(__name__)


async def reprocess(only_failed: bool, image_id: int | None) -> int:
    async with async_session_maker() as session:
        statement = select(ProductImage)
        if only_failed:
            statement = statement.where(ProductImage.processing_status == "failed")
        if image_id is not None:
            statement = statement.where(ProductImage.id == image_id)

        images = (await session.execute(statement)).scalars().all()
        if not images:
            print("No images matched.")
            return 0

        # Clear prior state so the worker regenerates and the no-upscale rule
        # can drop variants that are no longer warranted.
        for image in images:
            image.processing_status = "pending"
            image.processed_urls = None
            image.processing_error = None
        await session.commit()

        for image in images:
            enqueue_image_processing(image.id)

        print(f"Queued {len(images)} image(s) for regeneration.")
        return len(images)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--failed",
        action="store_true",
        help="only reprocess images whose last attempt failed",
    )
    parser.add_argument(
        "--id",
        type=int,
        help="reprocess a single ProductImage id",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    queued = asyncio.run(reprocess(args.failed, args.id))
    return 0 if queued else 1


if __name__ == "__main__":
    sys.exit(main())

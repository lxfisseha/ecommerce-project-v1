"""
Background image processing worker.

On upload the app stores the original and enqueues a job here. The job
resizes the original to 3 WebP variants (160/400/800) with Pillow, writes
them next to it, and records their keys on the ProductImage row. Templates
read those keys, so the browser never waits on a resize.
"""
import io
import logging
import sys
from pathlib import Path

from PIL import Image

from src.config import settings
from src.constants import VARIANT_PREFIX
from src.utils.storage import LocalStorage

logger = logging.getLogger(__name__)

# Variant name -> width in pixels
SIZES = {
    "thumb": 160,
    "medium": 400,
    "large": 800,
}

OUTPUT_FORMAT = "WEBP"
OUTPUT_QUALITY = 80


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    """Drop alpha onto white, since WebP variants are served without a matte."""
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def generate_variants(image_data: bytes, stem: str, storage: LocalStorage) -> dict:
    """Resize image_data to every width in SIZES and store the WebP variants."""
    img = Image.open(io.BytesIO(image_data))
    img.load()
    img = _flatten_to_rgb(img)

    variants = {}
    for name, width in SIZES.items():
        height = max(1, round(width * img.height / img.width))
        resized = img.resize((width, height), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        resized.save(buffer, format=OUTPUT_FORMAT, quality=OUTPUT_QUALITY, method=6)
        buffer.seek(0)

        key = f"{VARIANT_PREFIX}/{stem}_{width}w.webp"
        variants[name] = storage.write(key, buffer.read())

    return variants


def process_image_task(image_id: int) -> dict:
    """RQ job entry point. Must be importable at module level for unpickling."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlmodel import select

    from src.database import async_session_maker
    from src.features.products.models import ProductImage

    async def process() -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(ProductImage).where(ProductImage.id == image_id)
            )
            image = result.scalar_one_or_none()

            if not image:
                logger.error("Image %s not found", image_id)
                return {"status": "error", "message": "Image not found"}

            if image.processing_status == "completed":
                return {"status": "skipped", "message": "Already processed"}

            if not image.object_name:
                image.processing_status = "failed"
                image.processing_error = "No object_name on image record"
                await session.commit()
                return {"status": "error", "message": "No object_name"}

            image.processing_status = "processing"
            await session.commit()

            try:
                storage = LocalStorage()
                variants = generate_variants(
                    storage.read(image.object_name),
                    Path(image.object_name).stem,
                    storage,
                )
            except Exception as exc:
                logger.exception("Failed to process image %s", image_id)
                image.processing_status = "failed"
                image.processing_error = str(exc)
                await session.commit()
                return {"status": "error", "message": str(exc)}

            image.processed_urls = variants
            image.processing_status = "completed"
            image.processing_error = None
            from src.utils.datetime import utc_now
            image.processed_at = utc_now()
            await session.commit()
            return {"status": "completed", "variants": variants}

    return asyncio.run(process())


def enqueue_image_processing(image_id: int) -> str:
    """Queue a resize job for one ProductImage and return the RQ job id."""
    import redis
    from rq import Queue

    connection = redis.Redis.from_url(settings.REDIS_URL)
    job = Queue(connection=connection).enqueue(process_image_task, image_id)
    return job.id


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("usage: python -m src.scripts.process_images <image_id>")
        raise SystemExit(2)
    print(process_image_task(int(sys.argv[1])))

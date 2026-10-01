"""
Background image processing worker.

On upload the app stores the original and enqueues a job here. The job
resizes the original to 4 WebP variants (160/256/400/800) with Pillow, writes
them next to it, and records their keys on the ProductImage row. Templates
read those keys, so the browser never waits on a resize.
"""
import io
import logging
import sys
from pathlib import Path

from PIL import Image

from src.config import settings
from src.constants import BANNER_PREFIX, BANNER_VARIANT_NAME, VARIANT_PREFIX
from src.utils.storage import LocalStorage

logger = logging.getLogger(__name__)

# Variant name -> width in pixels. Must stay in step with
# _VARIANT_BY_WIDTH in src/templates_config.py, which maps a requested width
# back to a variant name; a mismatch makes media_url silently fall through to
# the original. test_image_sizes.py asserts the two match.
SIZES = {
    "icon": 160,
    "small": 256,
    "medium": 400,
    "large": 800,
}

# Per-tier WebP quality. Lower is fine for the small tiers because they are
# displayed at 64-216px, where compression artefacts are not resolvable. The
# 800w hero stays high because q80->65 shows on fabric texture.
VARIANT_QUALITY = {
    "icon": 65,
    "small": 70,
    "medium": 75,
    "large": 80,
}

OUTPUT_FORMAT = "WEBP"

# Seller banner image. Unlike product images this is a single variant, not a
# tier set: the homepage banner is decorative, rendered at 60% opacity behind a
# gradient scrim, so extra widths would buy nothing visible.
#
# 800w was chosen over a smaller width because the banner spans the full
# viewport width and is the first thing on the homepage. Quality is pinned to 75
# rather than the 80 used for the product hero, which is the difference between
# ~50 KB and ~155 KB on dense photographic fabric. BANNER_MAX_BYTES enforces the
# budget at generation time, because a hardcoded quality is only an average:
# a busy image can blow past it at any quality setting.
BANNER_WIDTH = 800
BANNER_QUALITY = 75
BANNER_MAX_BYTES = 50 * 1024

# Quality steps tried in order, lowest effort last. The loop stops at the first
# encoding that fits the budget, so a simple photo keeps the higher quality and
# only a genuinely busy one gets pushed down.
BANNER_QUALITY_LADDER = (75, 70, 65, 60, 55, 50, 45, 40)

# Widths tried if the whole quality ladder misses at BANNER_WIDTH. The banner
# spans the viewport so full width is preferred, but a budget that can be
# exceeded is not a budget, hence the fallback rather than a warning.
BANNER_WIDTH_FALLBACKS = (800, 640, 480, 400)


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
    """
    Resize to every width in SIZES that the source can actually support.

    Widths above the source are skipped rather than interpolated: an upscaled
    variant costs bytes and adds no detail, so it is strictly worse than the
    stored original. Templates fall back to the original for those widths.
    """
    img = Image.open(io.BytesIO(image_data))
    img.load()
    img = _flatten_to_rgb(img)

    variants = {}
    for name, width in SIZES.items():
        if width > img.width:
            logger.info(
                "Skipping %s variant for %s: source is %dpx wide", name, stem, img.width
            )
            continue

        height = max(1, round(width * img.height / img.width))
        resized = img.resize((width, height), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        resized.save(
            buffer,
            format=OUTPUT_FORMAT,
            quality=VARIANT_QUALITY[name],
            method=6,
        )
        buffer.seek(0)

        key = f"{VARIANT_PREFIX}/{stem}_{width}w.webp"
        variants[name] = storage.write(key, buffer.read())

    return variants


def _encode_banner(resized: Image.Image, width: int, quality: int) -> bytes:
    buffer = io.BytesIO()
    resized.save(buffer, format=OUTPUT_FORMAT, quality=quality, method=6)
    return buffer.getvalue()


def generate_banner(
    image_data: bytes,
    stem: str,
    storage: LocalStorage,
    max_bytes: int | None = None,
) -> dict:
    """
    Produce the single WebP variant the seller banner uses.

    Sellers store featured_image as a bare object key on the sellers row rather
    than a ProductImage row, so nothing queued a resize for it and the page served
    the untouched original. A 1600px JPEG landed at 304 KB on the homepage,
    against a 50 KB budget.

    Width is capped at BANNER_WIDTH and never upscaled: a banner narrower than
    the source keeps the original's aspect ratio, and an upscaled variant costs
    bytes while adding no detail.

    Quality walks down BANNER_QUALITY_LADDER until the encoding fits
    max_bytes, because the cost of a given quality depends entirely on the image
    and no single value can honour a budget. If the whole ladder still misses,
    the width is reduced in steps and the ladder is retried from the top, so the
    budget is actually enforceable. Only genuinely incompressible sources, such
    as raw noise, reach the final fallback.

    Returns a one-entry dict shaped like processed_urls so the template filter
    can treat both the same way, e.g. {"banner": "processed/sellers/<stem>_800w.webp"}.
    """
    img = Image.open(io.BytesIO(image_data))
    img.load()
    img = _flatten_to_rgb(img)

    if BANNER_WIDTH > img.width:
        logger.info(
            "Banner source is only %dpx wide; serving the original instead of "
            "upscaling to %dpx", img.width, BANNER_WIDTH,
        )
        return {}

    budget = BANNER_MAX_BYTES if max_bytes is None else max_bytes

    # Prefer full width at a quality that fits; only shrink width when the whole
    # quality ladder misses. The banner spans the viewport, so keeping 800w is
    # worth a few quality rungs.
    for width in BANNER_WIDTH_FALLBACKS:
        height = max(1, round(width * img.height / img.width))
        resized = img.resize((width, height), Image.Resampling.LANCZOS)

        for quality in BANNER_QUALITY_LADDER:
            payload = _encode_banner(resized, width, quality)
            if len(payload) <= budget:
                logger.info(
                    "Banner %s encoded at %dw q%d, %.1f KB (budget %.0f KB)",
                    stem, width, quality, len(payload) / 1024, budget / 1024,
                )
                key = f"{BANNER_PREFIX}/{stem}_{width}w.webp"
                return {BANNER_VARIANT_NAME: storage.write(key, payload)}

        logger.info(
            "Banner %s could not fit %.0f KB at %dw on any quality; "
            "reducing width", stem, budget / 1024, width,
        )

    # Genuinely incompressible, e.g. raw noise. Ship the smallest, lowest
    # quality encoding and say so: a slightly large banner beats a broken one,
    # and returning {} would hand the template the original we are avoiding.
    final_width = BANNER_WIDTH_FALLBACKS[-1]
    height = max(1, round(final_width * img.height / img.width))
    resized = img.resize((final_width, height), Image.Resampling.LANCZOS)
    payload = _encode_banner(resized, final_width, BANNER_QUALITY_LADDER[-1])
    logger.warning(
        "Banner %s could not be brought under %.0f KB; shipping %.1f KB at %dw q%d",
        stem, budget / 1024, len(payload) / 1024, final_width, BANNER_QUALITY_LADDER[-1],
    )
    key = f"{BANNER_PREFIX}/{stem}_{final_width}w.webp"
    return {BANNER_VARIANT_NAME: storage.write(key, payload)}


def store_banner_variant(image_data: bytes, object_name: str, storage: LocalStorage) -> dict:
    """
    Generate a banner variant for an already-stored object and clear any stale one.

    Wraps generate_banner so callers that have just written an original do not
    have to know about stems, prefixes or cleanup. Returns {} when no variant was
    produced, and in that case the old variant is removed so a replaced original
    cannot leave the template pointing at the wrong image.
    """
    stem = Path(object_name).stem
    # A previous run may have landed on any of the fallback widths, so every
    # candidate has to be cleared, not just BANNER_WIDTH.
    stale_keys = [
        f"{BANNER_PREFIX}/{stem}_{width}w.webp" for width in BANNER_WIDTH_FALLBACKS
    ]

    try:
        variants = generate_banner(image_data, stem, storage)
    except Exception:
        logger.exception("Banner generation failed for %s", object_name)
        for key in stale_keys:
            storage.delete(key)
        return {}

    if not variants:
        for key in stale_keys:
            storage.delete(key)
        return {}

    # If the new variant landed on a narrower fallback than before, the wider
    # file is no longer referenced and would otherwise be left behind.
    chosen = variants.get(BANNER_VARIANT_NAME)
    for key in stale_keys:
        if key != chosen:
            storage.delete(key)

    return variants


def process_image_task(image_id: int) -> dict:
    """RQ job entry point. Must be importable at module level for unpickling."""
    import asyncio

    # SQLModel needs every model class registered before the ORM can configure
    # relationships, otherwise Product.seller fails to resolve 'Seller'. The
    # app gets this for free via src.main's router imports; the worker has to
    # do it explicitly because it only ever touches ProductImage.
    from sqlmodel import select

    from src.database import async_session_maker
    from src.features.auth.models import Seller, OtpCode  # noqa: F401
    from src.features.orders.models import Order, OrderStatusLog  # noqa: F401
    from src.features.products.models import (  # noqa: F401
        Product,
        ProductAttribute,
        ProductImage,
        ProductTagLink,
        Tag,
    )

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
                stem = Path(image.object_name).stem

                # Clear variants from a previous run before regenerating. A
                # changed SIZES table or the no-upscale rule can leave files
                # that processed_urls no longer references. Delete the known
                # keys rather than a prefix: delete_prefix matches directories,
                # and this prefix is a filename stem.
                for stale_width in SIZES.values():
                    storage.delete(f"{VARIANT_PREFIX}/{stem}_{stale_width}w.webp")

                variants = generate_variants(
                    storage.read(image.object_name), stem, storage
                )
            except Exception as exc:
                logger.exception("Failed to process image %s", image_id)
                image.processing_status = "failed"
                image.processing_error = str(exc)
                await session.commit()
                return {"status": "error", "message": str(exc)}

            image.processed_urls = variants or None
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

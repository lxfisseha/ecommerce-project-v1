"""Shared storage helper for the sample seller banner.

add_seller.py and seed_production.py each fetch the same Unsplash image and
store it under sellers/<scope>/featured. Both previously stored only the
original, so the homepage banner served a 304 KB JPEG. The download and variant
generation live here so the two scripts cannot drift apart again.
"""
import logging
import urllib.request

from src.constants import BANNER_VARIANT_NAME
from src.scripts.process_images import store_banner_variant
from src.utils.storage import LocalStorage

logger = logging.getLogger(__name__)

SAMPLE_FEATURED_IMAGE_URL = (
    "https://images.unsplash.com/photo-1547949003-9792a18a2601"
    "?auto=format&fit=crop&q=80&w=1600"
)


def store_sample_featured_image(folder: str) -> tuple[str, dict | None]:
    """
    Fetch the sample banner, store it, and generate its variant.

    Returns (object_key, variants). The key is "" when the download fails and
    variants is None in that case, leaving the seller without a banner rather
    than one with a broken src.

    featured_image holds an object key rather than a URL, so storing the remote
    address directly would render as a broken image.
    """
    try:
        request = urllib.request.Request(
            SAMPLE_FEATURED_IMAGE_URL, headers={"User-Agent": "xcollections-seed/1.0"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
    except Exception as exc:
        logger.warning("Could not fetch sample featured image: %s", exc)
        return "", None

    if not data:
        return "", None

    storage = LocalStorage()
    object_name = storage.save(data, "featured.jpg", folder=folder)
    variants = store_banner_variant(data, object_name, storage) or None

    if variants:
        logger.info(
            "Sample banner variant: %s (%s)",
            variants.get(BANNER_VARIANT_NAME),
            folder,
        )
    else:
        logger.warning(
            "Sample banner for %s has no variant; the page will serve the "
            "%d KB original", folder, len(data) // 1024,
        )

    return object_name, variants

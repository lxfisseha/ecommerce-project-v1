from functools import lru_cache
import os

from fastapi.templating import Jinja2Templates
from fastapi import Request
from markupsafe import Markup


def csrf_token_context_processor(request: Request):
    return {"csrf_token": request.scope.get("csrf_token")}


def cart_count_context_processor(request: Request):
    from src.features.buyer.services import CartService

    return {"cart_count": CartService.count(request)}


_MEDIA_PREFIX = "/media"

# Variant name -> pixel width, mirroring SIZES in src.scripts.process_images.
# If the two drift apart, media_url falls through to the stored original with
# no error, so test_image_sizes.py asserts they match exactly.
_VARIANT_BY_WIDTH = {160: "icon", 256: "small", 400: "medium", 800: "large"}
_VARIANT_WIDTHS = sorted(_VARIANT_BY_WIDTH)


def _nearest_variant(width: int) -> str:
    """Smallest generated width that covers the request, else the largest."""
    for candidate in _VARIANT_WIDTHS:
        if candidate >= width:
            return _VARIANT_BY_WIDTH[candidate]
    return _VARIANT_BY_WIDTH[_VARIANT_WIDTHS[-1]]


def media_url(image, width: int = 400) -> str:
    """
    URL for a ProductImage at the nearest pre-generated width.

    Falls back to the stored original until the worker has written variants,
    so a freshly uploaded image is visible immediately. Also accepts a bare
    object key, for columns like seller.featured_image that have no variants.
    """
    if not image:
        return ""
    if isinstance(image, str):
        return f"{_MEDIA_PREFIX}/{image}"

    variants = getattr(image, "processed_urls", None) or {}
    key = variants.get(_nearest_variant(width)) or getattr(image, "object_name", "")
    return f"{_MEDIA_PREFIX}/{key}" if key else ""


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache(maxsize=1)
def _read_inline_css(rel_path: str) -> str:
    """Read a CSS file (cached) so it can be inlined to avoid render-blocking requests."""
    full = os.path.normpath(os.path.join(_PROJECT_ROOT, rel_path))
    try:
        with open(full, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def inline_css(rel_path: str) -> Markup:
    return Markup(_read_inline_css(rel_path))


templates = Jinja2Templates(
    directory="src/templates",
    context_processors=[csrf_token_context_processor, cart_count_context_processor]
)
templates.env.filters["media_url"] = media_url
templates.env.filters["inline_css"] = inline_css

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

# Key under which a seller banner variant is stored. Imported from constants
# rather than re-spelled so the writer in process_images and this reader cannot
# drift, which is the same failure mode _VARIANT_BY_WIDTH is guarded against.
# src.constants is used rather than src.scripts.process_images to keep Pillow
# and the storage layer out of the request path.
from src.constants import BANNER_VARIANT_NAME

# Variant name -> pixel width, mirroring SIZES in src.scripts.process_images.
# If the two drift apart, media_url falls through to the stored original with
# no error, so test_image_sizes.py asserts they match exactly.
_VARIANT_BY_WIDTH = {160: "icon", 320: "small", 400: "medium", 800: "large"}
_VARIANT_WIDTHS = sorted(_VARIANT_BY_WIDTH)

# Largest variant offered by product grid cards. A grid cell renders at
# 158-347 CSS px, but the browser multiplies `sizes` by device pixel ratio, so a
# 2x phone asks for ~352 device px and would otherwise pull the 800w file at
# ~52 KB per card.
#
# 320 is what makes the 320w tier reachable: uncapped, GRID_WIDTHS would drop to
# a single 160w candidate with no srcset at all, so the cap and the tier table
# have to move together or the change is invisible. At 320 a 2x phone is a 1.10x
# upscale instead of 1.38x, and a 12-card page costs ~114 KB against ~80 KB at
# the old 256w cap. The 800w tier stays for the product hero, the one context
# that genuinely needs it.
GRID_MAX_WIDTH = 320
GRID_WIDTHS = [w for w in _VARIANT_WIDTHS if w <= GRID_MAX_WIDTH]

# Range the product hero offers. The hero renders at 596-720 CSS px and its
# `sizes` never drops below 390px, so it has no use for the 160/320 card
# tiers, while it is the one context that legitimately wants the big file.
#
# Both bounds are pinned explicitly rather than implied by "the whole tier
# list": adding a larger variant later must not silently inflate every product
# page, and the gallery JS and the <picture> cannot disagree about the range.
HERO_MIN_WIDTH = 400
HERO_MAX_WIDTH = 800
HERO_WIDTHS = [w for w in _VARIANT_WIDTHS if HERO_MIN_WIDTH <= w <= HERO_MAX_WIDTH]


def hero_srcset(image) -> str:
    """srcset for the product hero, limited to HERO_WIDTHS."""
    return _srcset(image, HERO_WIDTHS)


def _srcset(image, widths: list[int]) -> str:
    """
    Join media_url candidates, dropping widths that resolve to the same file.

    Before the worker has written variants, media_url returns the stored
    original for every width. Emitting all of them would list one URL under
    several descriptors, so a browser would download the same file per
    candidate and reserve the wrong box. Keep the widest descriptor per
    distinct URL instead.
    """
    if not image:
        return ""
    by_url: dict[str, int] = {}
    for width in widths:
        by_url[media_url(image, width)] = width
    return ", ".join(f"{url} {width}w" for url, width in by_url.items())


def grid_srcset(image) -> str:
    """
    srcset for a grid card, limited to GRID_WIDTHS.

    Kept here rather than in each template so the cap is changed in one place
    and cannot drift between the buyer and dashboard grids.
    """
    return _srcset(image, GRID_WIDTHS)


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
    object key, for columns that genuinely have no variants.
    """
    if not image:
        return ""
    if isinstance(image, str):
        return f"{_MEDIA_PREFIX}/{image}"

    variants = getattr(image, "processed_urls", None) or {}
    key = variants.get(_nearest_variant(width)) or getattr(image, "object_name", "")
    return f"{_MEDIA_PREFIX}/{key}" if key else ""


def seller_banner_url(seller) -> str:
    """
    URL for a seller's homepage banner, preferring the generated variant.

    seller.featured_image is a bare object key on the sellers row, not a
    ProductImage, so passing it to media_url returns the original no matter what
    width is requested. That silently shipped a 304 KB JPEG as the first image
    on the homepage. The banner has exactly one variant, so there is no width
    to choose between and this filter takes no width argument by design.

    Falls back to the original when no variant exists, so a seller whose banner
    has not been processed yet still renders an image.
    """
    if seller is None:
        return ""
    key = getattr(seller, "featured_image", None)
    if not key:
        return ""

    variants = getattr(seller, "featured_image_variants", None) or {}
    banner_key = variants.get(BANNER_VARIANT_NAME) or key
    return f"{_MEDIA_PREFIX}/{banner_key}"


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
templates.env.filters["seller_banner_url"] = seller_banner_url
templates.env.filters["grid_srcset"] = grid_srcset
templates.env.filters["hero_srcset"] = hero_srcset
templates.env.filters["inline_css"] = inline_css
templates.env.globals["hero_widths"] = HERO_WIDTHS

# The banner's generated width, so the template's intrinsic size follows the
# worker instead of being a literal that goes stale when BANNER_WIDTH changes.
# Imported from src.constants rather than src.scripts.process_images to keep
# Pillow and the storage layer out of the request path.
from src.constants import BANNER_WIDTH as _BANNER_WIDTH

templates.env.globals["banner_width"] = _BANNER_WIDTH

# Storefront identity, injected rather than written into ~20 templates. The
# brand used to be a literal in every page title, both header wordmarks, the
# packing slip and the SMS bodies, which made a rename a 26-site find-replace
# where a single miss left a live page on the old brand.
from src.constants import SITE_NAME, SITE_SUPPORT_EMAIL, SITE_TELEGRAM_HANDLE

templates.env.globals["site_name"] = SITE_NAME
templates.env.globals["site_support_email"] = SITE_SUPPORT_EMAIL
templates.env.globals["site_telegram_handle"] = SITE_TELEGRAM_HANDLE

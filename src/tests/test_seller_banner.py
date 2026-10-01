"""Tests for the seller banner variant.

The homepage banner used to serve the stored original because featured_image is
a bare object key rather than a ProductImage row, so nothing generated a
variant for it. That shipped a 304 KB JPEG as the first image on the page.
"""
import io

import pytest
from PIL import Image

from src.constants import BANNER_PREFIX, BANNER_VARIANT_NAME
from src.scripts.process_images import (
    BANNER_MAX_BYTES,
    BANNER_QUALITY_LADDER,
    BANNER_WIDTH,
    generate_banner,
    store_banner_variant,
)


class FakeStorage:
    """In-memory stand-in for LocalStorage, recording writes and deletes."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def write(self, object_name: str, data: bytes) -> str:
        self.files[object_name] = data
        return object_name

    def delete(self, object_name: str) -> bool:
        self.deleted.append(object_name)
        return self.files.pop(object_name, None) is not None

    def read(self, object_name: str) -> bytes:
        return self.files[object_name]


def photo_jpeg(width: int = 1600, height: int = 1067, quality: int = 88) -> bytes:
    """
    A photographic-looking source: smooth gradients plus a little grain.

    Flat colour would compress to almost nothing and make a budget test pass for
    the wrong reason. Per-pixel hash noise would be worse in the other
    direction: it is incompressible at every quality and width, so no real
    photograph behaves that way and a test built on it would only ever exercise
    the last-resort fallback.
    """
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for x in range(width):
        for y in range(height):
            r = int(120 + 100 * ((x / width) - 0.5))
            g = int(90 + 80 * ((y / height) - 0.5))
            b = int(160 - 70 * ((x + y) / (width + height)))
            # Deterministic low-amplitude grain, ±6 levels.
            grain = ((x * 31 + y * 17) % 13) - 6
            pixels[x, y] = (
                max(0, min(255, r + grain)),
                max(0, min(255, g + grain)),
                max(0, min(255, b + grain)),
            )
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def noise_jpeg(width: int = 1600, height: int = 1067) -> bytes:
    """Per-pixel hash noise: incompressible, used only to force the fallback."""
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for x in range(width):
        for y in range(height):
            pixels[x, y] = ((x * 7 + y * 13) % 256, (x * 31) % 256, (y * 17) % 256)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


class TestBannerBudget:
    """The banner must fit a 50 KB budget whatever the source looks like."""

    def test_fits_the_budget_for_a_noisy_source(self):
        storage = FakeStorage()
        variants = generate_banner(photo_jpeg(), "stem", storage)
        key = variants[BANNER_VARIANT_NAME]
        assert len(storage.files[key]) <= BANNER_MAX_BYTES, (
            f"banner came to {len(storage.files[key]) / 1024:.1f} KB, "
            f"over the {BANNER_MAX_BYTES / 1024:.0f} KB budget"
        )

    def test_beats_the_original_by_a_wide_margin(self):
        """The bug was a 304 KB JPEG; the fix must not merely improve on it."""
        original = photo_jpeg()
        storage = FakeStorage()
        variants = generate_banner(original, "stem", storage)
        key = variants[BANNER_VARIANT_NAME]
        assert len(storage.files[key]) * 3 < len(original)

    def test_output_is_webp(self):
        storage = FakeStorage()
        key = generate_banner(photo_jpeg(), "stem", storage)[BANNER_VARIANT_NAME]
        assert Image.open(io.BytesIO(storage.files[key])).format == "WEBP"

    def test_width_is_the_configured_banner_width(self):
        storage = FakeStorage()
        key = generate_banner(photo_jpeg(), "stem", storage)[BANNER_VARIANT_NAME]
        assert Image.open(io.BytesIO(storage.files[key])).width == BANNER_WIDTH

    def test_preserves_aspect_ratio(self):
        storage = FakeStorage()
        key = generate_banner(photo_jpeg(1600, 1000), "stem", storage)[BANNER_VARIANT_NAME]
        width, height = Image.open(io.BytesIO(storage.files[key])).size
        assert (width, height) == (BANNER_WIDTH, round(BANNER_WIDTH * 1000 / 1600))

    def test_ships_a_variant_even_when_nothing_fits(self):
        """
        A banner over budget is still better than the original we are trying to
        avoid, so a variant is returned rather than an empty dict. An empty dict
        would make the template fall back to the 304 KB original.
        """
        storage = FakeStorage()
        variants = generate_banner(photo_jpeg(), "stem", storage, max_bytes=0)
        assert variants, "must still return a variant when over budget"
        assert len(storage.files[variants[BANNER_VARIANT_NAME]]) > 0

    def test_reduces_width_rather_than_breaching_the_budget(self):
        """
        The source here is per-pixel noise, which will not compress at any
        quality. The width fallback exists so the budget still holds rather
        than being a number in a comment.
        """
        storage = FakeStorage()
        variants = generate_banner(noise_jpeg(), "stem", storage)
        key = variants[BANNER_VARIANT_NAME]
        assert len(storage.files[key]) <= BANNER_MAX_BYTES
        assert Image.open(io.BytesIO(storage.files[key])).width < BANNER_WIDTH

    def test_prefers_full_width_for_a_photograph(self):
        """
        A real photograph fits the budget at 800w, and the banner spans the
        viewport, so it must not be shrunk to satisfy a budget it already meets.
        """
        storage = FakeStorage()
        key = generate_banner(photo_jpeg(), "stem", storage)[BANNER_VARIANT_NAME]
        assert f"_{BANNER_WIDTH}w.webp" in key
        assert Image.open(io.BytesIO(storage.files[key])).width == BANNER_WIDTH


class TestBannerNoUpscale:
    def test_returns_nothing_for_a_source_narrower_than_the_banner(self):
        storage = FakeStorage()
        assert generate_banner(photo_jpeg(500, 400), "stem", storage) == {}
        assert storage.files == {}

    def test_does_not_upscale_a_small_source(self):
        storage = FakeStorage()
        generate_banner(photo_jpeg(500, 400), "stem", storage)
        assert not any(name.endswith("webp") for name in storage.files)


class TestStoreBannerVariant:
    def test_writes_under_the_banner_prefix(self):
        storage = FakeStorage()
        key = store_banner_variant(photo_jpeg(), "sellers/1/featured/x.jpg", storage)[
            BANNER_VARIANT_NAME
        ]
        assert key.startswith(f"{BANNER_PREFIX}/")
        assert key.endswith(f"_{BANNER_WIDTH}w.webp")

    def test_derives_the_stem_from_the_object_name(self):
        storage = FakeStorage()
        key = store_banner_variant(photo_jpeg(), "sellers/1/featured/abc.jpg", storage)[
            BANNER_VARIANT_NAME
        ]
        assert "abc" in key

    def test_removes_a_stale_variant_when_generation_fails(self):
        """
        Replacing an original with an unprocessable one must not leave the
        template pointing at the previous image's variant.
        """
        storage = FakeStorage()
        corrupt = b"not an image"
        key = store_banner_variant(corrupt, "sellers/1/featured/abc.jpg", storage)
        assert key == {}
        assert storage.deleted, "a stale variant should have been removed"

    def test_removes_a_stale_variant_when_the_source_is_too_small(self):
        storage = FakeStorage()
        key = store_banner_variant(photo_jpeg(400, 300), "sellers/1/featured/abc.jpg", storage)
        assert key == {}
        assert storage.deleted


class TestVariantName:
    def test_banner_key_is_shared_with_the_template_filter(self):
        """
        A mismatch between the writer's key and the reader's would silently
        restore the original, which is the exact bug being fixed.
        """
        from src.constants import BANNER_VARIANT_NAME as writer_name
        from src.templates_config import BANNER_VARIANT_NAME as reader_name

        assert writer_name == reader_name

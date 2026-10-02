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
    BANNER_WIDTH_FALLBACKS,
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
        A real photograph fits the budget at full width, and the banner spans the
        viewport, so it must not be shrunk to satisfy a budget it already meets.
        """
        storage = FakeStorage()
        key = generate_banner(photo_jpeg(), "stem", storage)[BANNER_VARIANT_NAME]
        assert f"_{BANNER_WIDTH}w.webp" in key
        assert Image.open(io.BytesIO(storage.files[key])).width == BANNER_WIDTH

    def test_reaches_the_top_quality_rung_for_an_easy_image(self):
        """
        A photograph should land on the ladder's best rung, not merely fit.

        Worth pinning because the ceiling and the budget are independent: a
        ceiling of 75 satisfies every byte-budget test while quietly capping
        quality far below what the budget allows.

        Identified by re-encoding from the source, never from the stored WebP.
        WebP is lossy, so a second encode of an already-compressed file comes out
        smaller than the first and would make any rung look like the winner.
        """
        source = photo_jpeg()
        storage = FakeStorage()
        key = generate_banner(source, "stem", storage)[BANNER_VARIANT_NAME]
        payload = storage.files[key]

        img = Image.open(io.BytesIO(source)).convert("RGB")
        width = BANNER_WIDTH
        resized = img.resize(
            (width, round(width * img.height / img.width)),
            Image.Resampling.LANCZOS,
        )

        expected_rung = None
        for quality in BANNER_QUALITY_LADDER:
            candidate = io.BytesIO()
            resized.save(candidate, format="WEBP", quality=quality, method=6)
            if len(candidate.getvalue()) <= BANNER_MAX_BYTES:
                expected_rung = quality
                expected_bytes = candidate.getvalue()
                break

        assert expected_rung == BANNER_QUALITY_LADDER[0], (
            "fixture no longer reaches the top rung, so this test would pass "
            "for the wrong reason"
        )
        assert payload == expected_bytes, (
            f"banner did not encode at the top rung q{expected_rung}"
        )


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


class TestWidthAndQualityConfig:
    """
    Guards on the shape of the generation settings.

    These are invariants rather than assertions about current numbers, so they
    survive someone retuning the banner without becoming noise.
    """

    def test_no_fallback_width_exceeds_the_primary(self):
        """
        The fallback list is the set of widths the ladder may settle on, so a
        value above BANNER_WIDTH would let a banner ship larger than the cap.
        Appending to that tuple is the easy mistake, and it fails silently.
        """
        assert BANNER_WIDTH_FALLBACKS[0] == BANNER_WIDTH
        too_wide = [w for w in BANNER_WIDTH_FALLBACKS if w > BANNER_WIDTH]
        assert not too_wide, (
            f"fallback widths exceed the primary {BANNER_WIDTH}w: {too_wide}"
        )

    def test_fallback_widths_decrease(self):
        """Monotonic order is what makes the ladder a ladder."""
        assert list(BANNER_WIDTH_FALLBACKS) == sorted(
            BANNER_WIDTH_FALLBACKS, reverse=True
        )

    def test_quality_ladder_starts_at_its_ceiling(self):
        """
        The loop stops at the first rung that fits, so the ladder's first entry
        is the best quality any image can receive and it only ever walks down.

        Capping this low makes the byte budget unreachable: a larger budget then
        buys nothing, because no rung above the cap is ever attempted. That is
        what made a 64 KB budget unusable while the ceiling sat at 75.
        """
        assert BANNER_QUALITY_LADDER[0] == max(BANNER_QUALITY_LADDER)

    def test_quality_ladder_descends(self):
        assert list(BANNER_QUALITY_LADDER) == sorted(
            BANNER_QUALITY_LADDER, reverse=True
        )

    def test_quality_rungs_are_valid_webp_qualities(self):
        for quality in BANNER_QUALITY_LADDER:
            assert 1 <= quality <= 100, f"{quality} is out of range for libwebp"

    def test_widths_are_positive(self):
        for width in BANNER_WIDTH_FALLBACKS:
            assert width > 0, f"{width} is not a usable width"

    def test_worker_and_template_agree_on_the_banner_width(self):
        """
        src.constants feeds both the worker and the template's intrinsic width.

        They are separate declarations on purpose, so they can drift, and a
        mismatch reserves the wrong box before the banner loads without breaking
        anything visibly.
        """
        from src.constants import BANNER_WIDTH as declared

        assert declared == BANNER_WIDTH
        from src.templates_config import templates as tpl

        assert tpl.env.globals["banner_width"] == BANNER_WIDTH


class TestVariantName:
    def test_banner_key_is_shared_with_the_template_filter(self):
        """
        A mismatch between the writer's key and the reader's would silently
        restore the original, which is the exact bug being fixed.
        """
        from src.constants import BANNER_VARIANT_NAME as writer_name
        from src.templates_config import BANNER_VARIANT_NAME as reader_name

        assert writer_name == reader_name

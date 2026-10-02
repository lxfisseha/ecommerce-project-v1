import io

import pytest
from PIL import Image

from src.scripts.process_images import SIZES, VARIANT_QUALITY, generate_variants


@pytest.fixture
def jpeg_bytes():
    """A 1200px source, wider than every tier, so nothing is skipped."""
    buf = io.BytesIO()
    Image.new("RGB", (1200, 900), (10, 120, 200)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


@pytest.fixture
def noisy_jpeg_bytes():
    """High-detail content, so quality changes are measurable in the bytes."""
    import random

    rng = random.Random(7)
    img = Image.new("RGB", (1200, 900))
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256))
                 for _ in range(1200 * 900)])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


class _FakeStorage:
    def __init__(self):
        self.written = {}

    def write(self, key, data):
        self.written[key] = data
        return key


def test_generates_one_variant_per_size(jpeg_bytes):
    storage = _FakeStorage()
    variants = generate_variants(jpeg_bytes, "abc", storage)

    assert set(variants) == set(SIZES)
    assert set(variants.values()) == set(storage.written)
    assert len(storage.written) == len(SIZES)


def test_variant_widths_match_requested(jpeg_bytes):
    storage = _FakeStorage()
    variants = generate_variants(jpeg_bytes, "abc", storage)

    for name, width in SIZES.items():
        with Image.open(io.BytesIO(storage.written[variants[name]])) as img:
            assert img.format == "WEBP"
            assert img.width == width
            assert img.height == round(width * 900 / 1200)


def test_variant_keys_are_predictable(jpeg_bytes):
    storage = _FakeStorage()
    variants = generate_variants(jpeg_bytes, "abc", storage)

    assert variants["icon"] == "processed/products/abc_160w.webp"
    assert variants["small"] == "processed/products/abc_320w.webp"
    assert variants["medium"] == "processed/products/abc_400w.webp"
    assert variants["large"] == "processed/products/abc_800w.webp"


def test_all_four_tiers_are_used_by_the_templates():
    """A tier nobody references is wasted work and wasted disk."""
    import pathlib
    import re

    templates = pathlib.Path(__file__).resolve().parents[1] / "templates"
    offered = set()
    for path in templates.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        offered |= {int(w) for w in re.findall(r"media_url\(\d+\)\s*\}\}\s*(\d+)w", text)}
    assert offered == set(SIZES.values()), (
        f"templates offer {sorted(offered)}, worker generates {sorted(SIZES.values())}"
    )


class TestPerTierQuality:

    def test_each_tier_uses_its_own_quality(self, noisy_jpeg_bytes):
        """
        A single quality for all tiers wastes bytes on the small ones and
        still under-serves the hero. Each tier must encode at its own value.
        """
        import io as _io

        from src.scripts.process_images import _flatten_to_rgb

        storage = _FakeStorage()
        variants = generate_variants(noisy_jpeg_bytes, "q", storage)

        img = _flatten_to_rgb(Image.open(_io.BytesIO(noisy_jpeg_bytes)))
        img.load()

        def encode(width, quality):
            height = max(1, round(width * img.height / img.width))
            resized = img.resize((width, height), Image.Resampling.LANCZOS)
            buf = _io.BytesIO()
            resized.save(buf, format="WEBP", quality=quality, method=6)
            return buf.getvalue()

        for name, width in SIZES.items():
            expected = encode(width, VARIANT_QUALITY[name])
            assert storage.written[variants[name]] == expected, (
                f"{name} tier did not encode at its configured quality"
            )

        icon_bytes = len(storage.written[variants["icon"]])
        large_bytes = len(storage.written[variants["large"]])
        assert icon_bytes < large_bytes, "lower quality should produce fewer bytes"

    def test_lower_quality_actually_saves_bytes(self, noisy_jpeg_bytes):
        storage = _FakeStorage()
        variants = generate_variants(noisy_jpeg_bytes, "q", storage)
        icon_bytes = len(storage.written[variants["icon"]])
        large_bytes = len(storage.written[variants["large"]])
        # 160px at q65 should be far smaller than 800px at q80.
        assert icon_bytes < large_bytes / 3


class TestNoUpscaling:

    def test_source_wider_than_every_tier_gets_all(self, jpeg_bytes):
        storage = _FakeStorage()
        variants = generate_variants(jpeg_bytes, "big", storage)
        assert len(variants) == len(SIZES)

    def test_variant_wider_than_source_is_skipped(self):
        """
        Upscaling adds bytes without detail, so a 400px source must not get
        an 800w variant. Templates fall back to the stored original.
        """
        buf = io.BytesIO()
        Image.new("RGB", (400, 300), (200, 40, 90)).save(buf, format="JPEG", quality=90)
        storage = _FakeStorage()

        variants = generate_variants(buf.getvalue(), "small", storage)

        assert set(variants) == {"icon", "small", "medium"}
        assert "large" not in variants
        assert not any("800w" in key for key in storage.written)

    def test_mid_tier_is_skipped_for_a_200px_source(self):
        """320w must be skipped too, not just the largest tier."""
        buf = io.BytesIO()
        Image.new("RGB", (200, 150)).save(buf, format="JPEG", quality=90)
        storage = _FakeStorage()

        variants = generate_variants(buf.getvalue(), "mid", storage)

        assert set(variants) == {"icon"}

    def test_source_exactly_at_variant_width_is_kept(self):
        buf = io.BytesIO()
        Image.new("RGB", (400, 300)).save(buf, format="JPEG", quality=90)
        storage = _FakeStorage()

        variants = generate_variants(buf.getvalue(), "exact", storage)

        assert "medium" in variants, "a 400px source should still yield the 400w variant"

    def test_all_variants_skipped_for_tiny_source(self):
        buf = io.BytesIO()
        Image.new("RGB", (100, 80)).save(buf, format="JPEG", quality=90)
        storage = _FakeStorage()

        variants = generate_variants(buf.getvalue(), "tiny", storage)

        assert variants == {}
        assert storage.written == {}


class TestImageHandling:

    def test_transparency_is_flattened_to_white(self):
        buf = io.BytesIO()
        Image.new("RGBA", (900, 900), (255, 0, 0, 0)).save(buf, format="PNG")
        storage = _FakeStorage()

        variants = generate_variants(buf.getvalue(), "alpha", storage)

        with Image.open(io.BytesIO(storage.written[variants["icon"]])) as img:
            assert img.mode == "RGB"
            r, g, b = img.convert("RGB").getpixel((0, 0))
            assert r > 240 and g > 240 and b > 240

    def test_palette_image_is_converted(self):
        buf = io.BytesIO()
        Image.new("P", (900, 600)).save(buf, format="PNG")
        storage = _FakeStorage()

        variants = generate_variants(buf.getvalue(), "pal", storage)

        with Image.open(io.BytesIO(storage.written[variants["large"]])) as img:
            assert img.mode == "RGB"
            assert img.width == 800

    def test_grayscale_image_is_converted(self):
        buf = io.BytesIO()
        Image.new("L", (1200, 800), 128).save(buf, format="PNG")
        storage = _FakeStorage()

        variants = generate_variants(buf.getvalue(), "gray", storage)

        with Image.open(io.BytesIO(storage.written[variants["medium"]])) as img:
            assert img.mode == "RGB"
            assert img.width == 400

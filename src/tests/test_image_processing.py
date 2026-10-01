import io

import pytest
from PIL import Image

from src.scripts.process_images import SIZES, generate_variants


@pytest.fixture
def jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (1200, 900), (10, 120, 200)).save(buf, format="JPEG", quality=90)
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
    assert len(storage.written) == 3


def test_variant_widths_match_requested(jpeg_bytes):
    storage = _FakeStorage()
    variants = generate_variants(jpeg_bytes, "abc", storage)

    for name, width in SIZES.items():
        with Image.open(io.BytesIO(storage.written[variants[name]])) as img:
            assert img.format == "WEBP"
            assert img.width == width
            # aspect ratio preserved
            assert img.height == round(width * 900 / 1200)


def test_variant_keys_are_predictable(jpeg_bytes):
    storage = _FakeStorage()
    variants = generate_variants(jpeg_bytes, "abc", storage)

    assert variants["thumb"] == "processed/products/abc_160w.webp"
    assert variants["medium"] == "processed/products/abc_400w.webp"
    assert variants["large"] == "processed/products/abc_800w.webp"


def test_transparency_is_flattened_to_white():
    buf = io.BytesIO()
    Image.new("RGBA", (400, 400), (255, 0, 0, 0)).save(buf, format="PNG")
    storage = _FakeStorage()

    variants = generate_variants(buf.getvalue(), "alpha", storage)

    with Image.open(io.BytesIO(storage.written[variants["thumb"]])) as img:
        assert img.mode == "RGB"
        r, g, b = img.convert("RGB").getpixel((0, 0))
        assert r > 240 and g > 240 and b > 240


def test_palette_image_is_converted():
    buf = io.BytesIO()
    Image.new("P", (900, 600)).save(buf, format="PNG")
    storage = _FakeStorage()

    variants = generate_variants(buf.getvalue(), "pal", storage)

    with Image.open(io.BytesIO(storage.written[variants["large"]])) as img:
        assert img.mode == "RGB"
        assert img.width == 800


def test_small_image_is_not_upscaled(jpeg_bytes):
    """
    A 1200px source is wider than every generated size, so all three apply.
    The 800w tier is a genuine downscale here.
    """
    storage = _FakeStorage()
    variants = generate_variants(jpeg_bytes, "big", storage)

    with Image.open(io.BytesIO(storage.written[variants["large"]])) as img:
        assert img.width == 800


def test_variant_wider_than_source_is_skipped():
    """
    Upscaling adds bytes without detail, so a 400px source must not get an
    800w variant. Templates then fall back to the stored original.
    """
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 40, 90)).save(buf, format="JPEG", quality=90)
    storage = _FakeStorage()

    variants = generate_variants(buf.getvalue(), "small", storage)

    assert set(variants) == {"thumb", "medium"}
    assert "large" not in variants
    assert not any("800w" in key for key in storage.written)


def test_source_exactly_at_variant_width_is_kept():
    buf = io.BytesIO()
    Image.new("RGB", (400, 300)).save(buf, format="JPEG", quality=90)
    storage = _FakeStorage()

    variants = generate_variants(buf.getvalue(), "exact", storage)

    assert "medium" in variants, "a 400px source should still yield the 400w variant"


def test_all_variants_skipped_for_tiny_source():
    buf = io.BytesIO()
    Image.new("RGB", (100, 80)).save(buf, format="JPEG", quality=90)
    storage = _FakeStorage()

    variants = generate_variants(buf.getvalue(), "tiny", storage)

    assert variants == {}
    assert storage.written == {}

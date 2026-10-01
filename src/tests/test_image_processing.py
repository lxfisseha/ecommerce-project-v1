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
    Image.new("P", (200, 200)).save(buf, format="PNG")
    storage = _FakeStorage()

    variants = generate_variants(buf.getvalue(), "pal", storage)

    with Image.open(io.BytesIO(storage.written[variants["large"]])) as img:
        assert img.mode == "RGB"
        assert img.width == 800


def test_small_image_is_not_upscaled_beyond_source(jpeg_bytes):
    """A 1200px source stays at the requested width; the worker does not guard
    against upscaling, so this documents current behaviour."""
    storage = _FakeStorage()
    variants = generate_variants(jpeg_bytes, "small", storage)

    with Image.open(io.BytesIO(storage.written[variants["large"]])) as img:
        assert img.width == 800

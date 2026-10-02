from types import SimpleNamespace

from src.templates_config import media_url


def _image(object_name, processed_urls=None):
    return SimpleNamespace(object_name=object_name, processed_urls=processed_urls)


VARIANTS = {
    "icon": "processed/products/abc_160w.webp",
    "small": "processed/products/abc_320w.webp",
    "medium": "processed/products/abc_400w.webp",
    "large": "processed/products/abc_800w.webp",
}


class TestMediaUrl:

    def test_exact_variant_widths(self):
        img = _image("products/originals/abc.jpg", VARIANTS)
        assert media_url(img, 160) == "/media/processed/products/abc_160w.webp"
        assert media_url(img, 320) == "/media/processed/products/abc_320w.webp"
        assert media_url(img, 400) == "/media/processed/products/abc_400w.webp"
        assert media_url(img, 800) == "/media/processed/products/abc_800w.webp"

    def test_width_snaps_up_to_next_variant(self):
        img = _image("products/originals/abc.jpg", VARIANTS)
        assert media_url(img, 200) == "/media/processed/products/abc_320w.webp"
        assert media_url(img, 321) == "/media/processed/products/abc_400w.webp"
        assert media_url(img, 401) == "/media/processed/products/abc_800w.webp"

    def test_width_above_largest_snaps_down(self):
        img = _image("products/originals/abc.jpg", VARIANTS)
        assert media_url(img, 4000) == "/media/processed/products/abc_800w.webp"

    def test_falls_back_to_original_while_pending(self):
        img = _image("products/originals/abc.jpg", None)
        assert media_url(img, 400) == "/media/products/originals/abc.jpg"

    def test_falls_back_when_variant_missing(self):
        img = _image("products/originals/abc.jpg", {"icon": VARIANTS["icon"]})
        assert media_url(img, 800) == "/media/products/originals/abc.jpg"

    def test_bare_object_key(self):
        assert media_url("sellers/1/featured/hero.jpg", 800) == "/media/sellers/1/featured/hero.jpg"

    def test_empty_inputs(self):
        assert media_url(None) == ""
        assert media_url("") == ""
        assert media_url(_image("")) == ""

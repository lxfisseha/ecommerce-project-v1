"""
Guard the image tier set and the `sizes` attributes on responsive images.

Two classes of bug are covered:

- Drift between the worker's SIZES and the template filter's
  _VARIANT_BY_WIDTH. A mismatch makes media_url fall through to the stored
  original with no error, so a new tier can be offered in a template that
  nothing ever generates.
- A `sizes` string that does not describe the layout it sits in. One
  copy-pasted value was applied to every context, telling a 96px cart
  thumbnail it needed 800px while a full-width hero on mobile was served
  160w.
"""
import pathlib
import re

import pytest

from src.scripts.process_images import SIZES, VARIANT_QUALITY
from src.templates_config import _VARIANT_BY_WIDTH

TEMPLATES = pathlib.Path(__file__).resolve().parents[1] / "templates"

# (template, expected substring of the sizes attribute)
EXPECTED = {
    "buyer/_product_grid.html": "(max-width: 767px) 45vw, (max-width: 1280px) 22vw, 286px",
    "products/_product_list_content.html": "(max-width: 640px) 90vw, (max-width: 1024px) 45vw, 300px",
    "buyer/_cart_content.html": "96px",
    "products/form.html": "(max-width: 768px) 45vw, 130px",
    "buyer_product_detail.html": "(max-width: 1024px) 100vw, 610px",
}

# Every image that offers a srcset must declare sizes; without it the browser
# assumes 100vw and picks the largest candidate.
SRCSET_TEMPLATES = [
    "buyer/_product_grid.html",
    "products/_product_list_content.html",
    "buyer/_cart_content.html",
    "products/form.html",
    "buyer_product_detail.html",
]


def read(rel: str) -> str:
    return (TEMPLATES / rel).read_text(encoding="utf-8")


class TestTierSet:

    def test_variant_map_matches_worker_sizes(self):
        """
        The two lists are a contract with no type checking between them.
        If they drift, media_url returns the original instead of a variant
        and nothing raises.
        """
        assert _VARIANT_BY_WIDTH == {w: name for name, w in SIZES.items()}

    def test_every_variant_has_a_quality(self):
        assert set(VARIANT_QUALITY) == set(SIZES)

    def test_quality_ladder_is_ordered(self):
        """
        Quality rises with display size. q80->65 on the hero is a visible
        regression on fabric texture; q65 on a 160px icon is free.
        """
        qualities = [VARIANT_QUALITY[name] for name in SIZES]
        assert qualities == sorted(qualities), f"expected ascending quality, got {qualities}"

    def test_quality_stays_in_a_sane_range(self):
        # Below 50 WebP produces blocking artefacts; above 90 wastes bytes.
        for name, q in VARIANT_QUALITY.items():
            assert 50 <= q <= 90, f"{name} quality {q} is outside 50-90"

    def test_smallest_tier_covers_the_smallest_box(self):
        """
        Checkout rows render at 64px. The smallest tier has to be wide enough
        to serve them, and not so wide that it is pure waste for them.
        """
        smallest_box_px = 64
        smallest_tier = min(SIZES.values())
        assert smallest_tier >= smallest_box_px, (
            f"smallest tier {smallest_tier}w cannot serve a {smallest_box_px}px box"
        )
        assert smallest_tier <= smallest_box_px * 3, (
            f"smallest tier {smallest_tier}w is more than 3x the {smallest_box_px}px box"
        )

    def test_largest_tier_covers_the_hero(self):
        """The hero can be 610px wide and needs upscaling headroom on retina."""
        assert max(SIZES.values()) >= 800


class TestTemplateWidths:

    def _offered_widths(self, rel: str) -> set[int]:
        body = read(rel)
        # `{{ x | media_url(400) }} 400w` pairs a request with its descriptor.
        return {
            int(descriptor)
            for descriptor in re.findall(r"media_url\(\d+\)\s*\}\}\s*(\d+)w", body)
        }

    @pytest.mark.parametrize("rel", SRCSET_TEMPLATES)
    def test_srcset_widths_are_generatable(self, rel):
        """
        Every width a template offers must exist in SIZES. Otherwise the
        descriptor advertises a file the worker never writes, and the browser
        picks a candidate that is really a different, smaller image.
        """
        offered = self._offered_widths(rel)
        assert offered, f"{rel} offers no media_url width descriptors"
        unknown = offered - set(SIZES.values())
        assert not unknown, f"{rel} advertises widths the worker cannot generate: {unknown}"

    @pytest.mark.parametrize("rel", SRCSET_TEMPLATES)
    def test_srcset_images_declare_sizes(self, rel):
        body = read(rel)
        sources = re.findall(r"<source\b[^>]*>", body, re.S)
        assert sources, f"{rel} is expected to contain <source srcset>"
        for tag in sources:
            assert "srcset" in tag
            assert "sizes" in tag, f"{rel}: <source> has srcset but no sizes"

    def test_cart_thumbnail_does_not_offer_800w(self):
        """A 96px box has no use for the 800w variant."""
        assert 800 not in self._offered_widths("buyer/_cart_content.html")


class TestSizesAttributes:

    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED.items()))
    def test_sizes_matches_layout(self, rel, expected):
        body = read(rel)
        assert f'sizes="{expected}"' in body, f'{rel} should declare sizes="{expected}"'

    def test_no_legacy_blanket_sizes_attribute(self):
        """The old copy-pasted string claimed 800px for every context."""
        offenders = []
        for path in TEMPLATES.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(r'sizes="([^"]*)"', text):
                if m.group(1) == "(max-width: 480px) 160px, (max-width: 768px) 400px, 800px":
                    offenders.append(path.relative_to(TEMPLATES).as_posix())
        assert not offenders, f"blanket 800px sizes still present in: {offenders}"

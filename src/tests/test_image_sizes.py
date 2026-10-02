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
from src.templates_config import (
    GRID_MAX_WIDTH,
    GRID_WIDTHS,
    HERO_MAX_WIDTH,
    HERO_MIN_WIDTH,
    HERO_WIDTHS,
    _VARIANT_BY_WIDTH,
)

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


def offered_widths(rel: str) -> set[int]:
    """
    Widths a template advertises, from either authoring style.

    Inline:  `{{ x | media_url(400) }} 400w`
    Filter:  `{{ x | grid_srcset }}`, whose widths come from GRID_WIDTHS.
    """
    body = read(rel)
    widths = {
        int(descriptor)
        for descriptor in re.findall(r"media_url\(\d+\)\s*\}\}\s*(\d+)w", body)
    }
    if "grid_srcset" in body:
        widths |= set(GRID_WIDTHS)
    if "hero_srcset" in body:
        widths |= set(HERO_WIDTHS)
    return widths


class TestTemplateWidths:

    @pytest.mark.parametrize("rel", SRCSET_TEMPLATES)
    def test_srcset_widths_are_generatable(self, rel):
        """
        Every width a template offers must exist in SIZES. Otherwise the
        descriptor advertises a file the worker never writes, and the browser
        picks a candidate that is really a different, smaller image.
        """
        offered = offered_widths(rel)
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
        assert 800 not in offered_widths("buyer/_cart_content.html")


class TestGridCap:
    """
    Grid cards are capped below the largest tier.

    A card renders at 158-347 CSS px, but the browser multiplies `sizes` by
    device pixel ratio, so a 3x phone requests ~528 device px. Without a cap
    it selects the 800w file and a 12-card page costs ~626 KB.
    """

    GRIDS = ["buyer/_product_grid.html", "products/_product_list_content.html"]

    def test_cap_excludes_the_hero_tier(self):
        assert GRID_MAX_WIDTH < max(SIZES.values()), (
            "the cap must actually exclude the largest tier to have any effect"
        )

    def test_cap_keeps_at_least_two_candidates(self):
        """Below two candidates there is no srcset to choose between."""
        assert len(GRID_WIDTHS) >= 2

    def test_cap_widths_are_generatable(self):
        assert set(GRID_WIDTHS) <= set(SIZES.values())

    def test_cap_is_itself_a_generatable_width(self):
        """
        The cap and the tier table are separate declarations, and a cap that
        matches no tier makes the tier above it unreachable.

        That is exactly what happened when the cap stayed at 256 while the tier
        moved to 320: GRID_WIDTHS collapsed to [160], leaving a single candidate
        with no srcset to choose between, while the 320w files were generated on
        every upload and never fetched.
        """
        assert GRID_MAX_WIDTH in SIZES.values(), (
            f"cap {GRID_MAX_WIDTH} matches no tier in {sorted(SIZES.values())}; "
            "the grid would not offer the next tier up"
        )

    @pytest.mark.parametrize("rel", GRIDS)
    def test_grids_use_the_shared_cap(self, rel):
        """Both grids must go through grid_srcset so the cap cannot drift."""
        assert "| grid_srcset" in read(rel), f"{rel} should use the shared grid_srcset filter"
        assert 800 not in offered_widths(rel)

    @pytest.mark.parametrize("rel", GRIDS)
    def test_grid_fallback_stays_on_the_cap(self, rel):
        """The <img> fallback must not point at a file the srcset withholds."""
        import re as _re

        fallback = _re.search(r'<img[^>]*src="\{\{[^}]*media_url\((\d+)\)', read(rel))
        assert fallback, f"{rel} should have an <img> fallback"
        assert int(fallback.group(1)) <= GRID_MAX_WIDTH, (
            f"{rel} fallback requests {fallback.group(1)}w, above the {GRID_MAX_WIDTH}w cap"
        )

    def test_product_detail_hero_still_gets_800w(self):
        """
        The cap is for cards, not the hero. The hero renders at 596-720px and
        is the one context that genuinely needs the large tier.
        """
        assert 800 in offered_widths("buyer_product_detail.html")


class TestHeroCap:
    """
    The hero is pinned at 800w explicitly.

    It happens to equal the largest tier today, but pinning it means adding a
    larger variant later will not quietly inflate every product page. It also
    keeps the gallery JS and the <picture> element on one source of truth.
    """

    HERO = "buyer_product_detail.html"

    def test_hero_cap_is_the_largest_tier_today(self):
        """If this fails, a larger tier was added and the hero ceiling needs a decision."""
        assert HERO_MAX_WIDTH == max(SIZES.values())

    def test_hero_floor_is_a_generatable_width(self):
        assert HERO_MIN_WIDTH in SIZES.values()

    def test_hero_widths_are_generatable(self):
        assert set(HERO_WIDTHS) <= set(SIZES.values())

    def _hero_img_tag(self) -> str:
        import re as _re

        match = _re.search(r"<img[^>]*id=\"main-product-image\"[^>]*>", read(self.HERO), _re.S)
        assert match, "hero <img> should be findable"
        return match.group(0)

    def test_hero_fallback_stays_on_the_cap(self):
        """The <img> fallback must not name a width above the cap."""
        import re as _re

        widths = _re.findall(r"media_url\((\d+)\)", self._hero_img_tag())
        assert widths, "hero <img> fallback should use media_url"
        assert int(widths[0]) <= HERO_MAX_WIDTH, (
            f"hero fallback requests {widths[0]}w, above the {HERO_MAX_WIDTH}w cap"
        )

    def test_hero_fallback_declares_matching_dimensions(self):
        """A fallback whose width/height disagree with its file reserves the wrong box."""
        import re as _re

        tag = self._hero_img_tag()
        requested = _re.search(r"media_url\((\d+)\)", tag)
        width = _re.search(r'width="(\d+)"', tag)
        height = _re.search(r'height="(\d+)"', tag)
        assert requested and width and height, (
            "hero <img> should declare width, height and a media_url request"
        )
        assert int(width.group(1)) == int(height.group(1)) == int(requested.group(1))
        assert int(requested.group(1)) == HERO_MAX_WIDTH

    def test_hero_cap_is_at_least_the_grid_cap(self):
        assert HERO_MAX_WIDTH >= GRID_MAX_WIDTH

    def test_hero_does_not_offer_card_only_tiers(self):
        """
        The hero's `sizes` floor is 390px, so 160/320 are never a valid pick.
        Offering them costs parse time and invites a future editor to wonder
        which one applies.

        Written as a set difference rather than listing 160 and 256 so this
        survives a future change to the card tiers.
        """
        card_widths = {w for w in SIZES.values() if w < HERO_MIN_WIDTH}
        assert min(HERO_WIDTHS) >= HERO_MIN_WIDTH
        assert not (card_widths & set(HERO_WIDTHS)), (
            f"hero offers card-only tiers: {card_widths & set(HERO_WIDTHS)}"
        )

    def _hero_fixed_sizes_clauses(self) -> list[int]:
        """Fixed-width clauses from the hero's `sizes`, excluding breakpoints."""
        import re as _re

        attr = _re.search(r'sizes="([^"]*)"', read(self.HERO))
        assert attr, "hero should declare a sizes attribute"
        # Drop any "(max-width: NNNpx)" prefixes; only the widths remain.
        stripped = _re.sub(r"\([^)]*\)", " ", attr.group(1))
        return [int(float(w)) for w in _re.findall(r"([\d.]+)px", stripped)]

    def test_hero_cap_covers_its_widest_sizes_clause(self):
        """
        The browser picks the *smallest candidate that covers* its target, so
        the binding constraint is on the ceiling, not the floor: the widest
        fixed `sizes` clause is the 610px desktop box and the cap must reach it.

        `100vw` is deliberately not checked. At DPR 1 a 1024px viewport wants
        1024px, which no tier can serve; that upscale is inherent to the hero
        and bounded by the largest tier, not something the cap controls.
        """
        widest = max(self._hero_fixed_sizes_clauses())
        assert max(HERO_WIDTHS) >= widest, (
            f"hero cap {max(HERO_WIDTHS)}w cannot cover its widest sizes "
            f"clause of {widest}px"
        )

    def test_hero_floor_is_not_needlessly_large(self):
        """
        A 320px phone at DPR 1 wants 320px. If the floor were 800w that phone
        would be served the hero ceiling, paying 52 KB for a 320px slot. One
        step of slack above a small viewport is acceptable; the cap is not.
        """
        assert min(HERO_WIDTHS) <= 400

    def test_hero_uses_the_shared_filter(self):
        assert "| hero_srcset" in read(self.HERO)

    def test_gallery_js_has_no_hardcoded_widths(self):
        """
        The gallery rewrites the srcset on a thumbnail click. A width literal in
        the <script> would drift from the config, so none may appear there.

        The <img> fallback and the width/height attributes outside the script
        are allowed to name 800: they are not srcset descriptors, and the
        fallback is checked against HERO_MAX_WIDTH separately.
        """
        import re as _re

        script = "\n".join(
            _re.findall(r"<script\b[^>]*>(.*?)</script>", read(self.HERO), _re.S)
        )
        assert script, "hero template should contain a script block"
        # Built from the tier table rather than written out, so the guard keeps
        # working after a width is added or renamed.
        pattern = r"\b(?:" + "|".join(str(w) for w in sorted(SIZES.values())) + r")w\b"
        assert not _re.search(pattern, script), (
            f"gallery script still hardcodes a srcset width descriptor: {pattern}"
        )
        assert not _re.search(r"media_url\(\d+\)", script), (
            "gallery script should take URLs from the gallery array, not media_url"
        )

    def test_gallery_js_reads_widths_from_config(self):
        assert "hero_widths" in read(self.HERO)


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

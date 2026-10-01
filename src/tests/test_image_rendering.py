"""Rendering assertions for the image srcset filters.

test_image_sizes.py checks the templates textually, which cannot catch a
filter that renders an empty or malformed srcset. These render the real
templates through Jinja and assert on the emitted markup.
"""

import json
import re

import pytest
from starlette.requests import Request

from src.templates_config import (
    GRID_MAX_WIDTH,
    GRID_WIDTHS,
    HERO_MAX_WIDTH,
    HERO_WIDTHS,
    templates,
)

PROCESSED = {
    "icon": "i.webp", "small": "s.webp",
    "medium": "m.webp", "large": "l.webp",
}


class Obj:
    """Permissive stand-in for template objects: any attribute yields another."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getattr__(self, k):
        return Obj()

    def __str__(self):
        return "x"

    def __iter__(self):
        return iter([])

    def __html__(self):
        return "x"

    def __getitem__(self, k):
        return Obj()

    def __len__(self):
        return 1

    def __bool__(self):
        return True

    def __format__(self, spec):
        return format(1234.5, spec or "")

    def __gt__(self, o):
        return False

    def __lt__(self, o):
        return False

    def __ge__(self, o):
        return True

    def __le__(self, o):
        return True

    def __eq__(self, o):
        return isinstance(o, Obj)


@pytest.fixture
def image() -> Obj:
    return Obj(image_tag="thumbnail", processed_urls=PROCESSED)


@pytest.fixture
def request_() -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/",
        "headers": [], "query_string": b"", "scheme": "http",
        "server": ("x", 80), "client": ("x", 1),
    })


def descriptors(srcset: str) -> list[int]:
    return [int(w) for w in re.findall(r"(\d+)w", srcset)]


def render(template: str, **ctx) -> str:
    request = ctx.pop("request_")
    # The seller-facing list template paginates; these tests care about the
    # image markup, so supply inert pagination rather than the real context.
    ctx.setdefault("current_page", 1)
    ctx.setdefault("total_pages", 1)
    return templates.env.get_template(template).render(
        request=request, csrf_token="t", **ctx
    )


class TestGridRender:
    GRIDS = ["buyer/_product_grid.html", "products/_product_list_content.html"]

    @pytest.mark.parametrize("rel", GRIDS)
    def test_srcset_offers_exactly_the_capped_widths(self, rel, image, request_):
        out = render(rel, request_=request_, products=[Obj(images=[image], id=26)])
        srcset = re.findall(r'srcset="([^"]*?)"\s+sizes', out, re.S)[0]
        assert descriptors(srcset) == GRID_WIDTHS
        assert max(descriptors(srcset)) <= GRID_MAX_WIDTH

    @pytest.mark.parametrize("rel", GRIDS)
    def test_no_descriptor_points_at_a_missing_file(self, rel, image, request_):
        """Every candidate must be one of the four generated variants."""
        out = render(rel, request_=request_, products=[Obj(images=[image], id=26)])
        srcset = re.findall(r'srcset="([^"]*?)"\s+sizes', out, re.S)[0]
        for url in re.findall(r"(/media/\S+?)\s+\d+w", srcset):
            assert url.rsplit("/", 1)[-1] in PROCESSED.values(), url

    @pytest.mark.parametrize("rel", GRIDS)
    def test_fallback_matches_a_candidate_in_the_srcset(self, rel, image, request_):
        """
        The <img> must not name a file the srcset withholds, and its width and
        height attributes must agree with each other so the box is reserved
        correctly before the image loads.
        """
        out = render(rel, request_=request_, products=[Obj(images=[image], id=26)])
        tag = re.search(r"<img[^>]*loading=\"lazy\"[^>]*>", out, re.S).group(0)
        width, height = re.findall(r'(?:width|height)="(\d+)"', tag)
        assert width == height == str(GRID_MAX_WIDTH)
        assert f"{width}w" in out

    def test_grid_renders_an_image_at_all(self, image, request_):
        out = render("buyer/_product_grid.html", request_=request_,
                     products=[Obj(images=[image], id=26)])
        assert "<picture>" in out


class TestHeroRender:
    HERO = "buyer_product_detail.html"

    def test_srcset_offers_exactly_the_hero_widths(self, image, request_):
        out = render(self.HERO, request_=request_, product_images=[image],
                     product=Obj(images=[image], id=26))
        srcset = re.findall(r'srcset="([^"]*?)"\s+sizes', out, re.S)[0]
        assert descriptors(srcset) == HERO_WIDTHS

    def test_hero_offers_the_cap(self, image, request_):
        out = render(self.HERO, request_=request_, product_images=[image],
                     product=Obj(images=[image], id=26))
        srcset = re.findall(r'srcset="([^"]*?)"\s+sizes', out, re.S)[0]
        assert max(descriptors(srcset)) == HERO_MAX_WIDTH

    def test_fallback_is_the_cap_width_and_declares_dimensions(self, image, request_):
        out = render(self.HERO, request_=request_, product_images=[image],
                     product=Obj(images=[image], id=26))
        tag = re.search(r'<img[^>]*id="main-product-image"[^>]*>', out, re.S).group(0)
        assert PROCESSED["large"] in tag
        assert re.findall(r'(?:width|height)="(\d+)"', tag) == [str(HERO_MAX_WIDTH)] * 2

    def test_gallery_entry_matches_the_rendered_picture(self, image, request_):
        """
        The gallery rewrites the srcset on a thumbnail click. If its stored
        entry diverged from the <picture>, the first click would visibly swap
        the image size.
        """
        out = render(self.HERO, request_=request_, product_images=[image],
                     product=Obj(images=[image], id=26))
        picture = " ".join(re.findall(r'srcset="([^"]*?)"\s+sizes', out, re.S)[0].split())
        entry = re.search(r'srcset: "([^"]+)"', out).group(1)
        assert entry == picture

    def test_gallery_fallback_is_the_hero_cap(self, image, request_):
        out = render(self.HERO, request_=request_, product_images=[image],
                     product=Obj(images=[image], id=26))
        fallback = re.search(r'fallback: "([^"]+)"', out).group(1)
        assert fallback.endswith(PROCESSED["large"])

    def test_hero_widths_are_serialised_for_js(self, image, request_):
        out = render(self.HERO, request_=request_, product_images=[image],
                     product=Obj(images=[image], id=26))
        widths = json.loads(re.search(r"const heroWidths = (\[.*?\]);", out).group(1))
        assert widths == HERO_WIDTHS

    def test_thumbnail_strip_still_uses_its_own_tier(self, image, request_):
        """The 64px thumbnails were deliberately left at 160w."""
        out = render(self.HERO, request_=request_, product_images=[image],
                     product=Obj(images=[image], id=26))
        thumbs = re.findall(r"<img[^>]*alt=\"Thumbnail\"[^>]*>", out)
        assert thumbs, "hero should render a thumbnail strip"
        # The 64-80px thumbnail buttons want the smallest tier, not the hero's.
        assert PROCESSED["icon"] in thumbs[0]
        assert PROCESSED["large"] not in thumbs[0]


class TestUnprocessedImage:
    """
    A freshly uploaded image has no variants yet.

    media_url falls back to the stored original so the page is never blank;
    the srcset should then carry a single candidate rather than four broken
    URLs pointing at files that do not exist.
    """

    def test_grid_srcset_degrades_to_the_original(self, request_):
        fresh = Obj(image_tag="thumbnail", processed_urls={})
        out = render("buyer/_product_grid.html", request_=request_,
                     products=[Obj(images=[fresh], id=26)])
        srcset = re.findall(r'srcset="([^"]*?)"\s+sizes', out, re.S)[0]
        widths = descriptors(srcset)
        assert widths, "srcset should not be empty"
        assert len(set(widths)) == 1, f"expected one candidate, got {widths}"

    def test_missing_image_renders_no_picture(self, request_):
        out = render("buyer/_product_grid.html", request_=request_,
                     products=[Obj(images=[], id=26)])
        assert "<picture>" not in out
        assert "<img" not in out

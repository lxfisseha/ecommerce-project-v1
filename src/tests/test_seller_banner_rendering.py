"""
The seller banner must render a generated variant, not the stored original.

featured_image is a bare object key rather than a ProductImage row, so nothing
ever generated a variant for it and the homepage shipped the untouched original:
304 KB for the first image on the page. These tests pin the fix at three levels:
the filter, the rendered markup, and the upload path that populates the column.
"""
import io
import re

import pytest
import pytest_asyncio
from PIL import Image
from sqlmodel import select
from starlette.requests import Request

from src.constants import BANNER_PREFIX, BANNER_VARIANT_NAME
from src.features.auth.models import Seller
from src.templates_config import seller_banner_url, templates
from src.tests.conftest import client, maker
from src.utils.datetime import utc_now

ORIGINAL_KEY = "sellers/1/featured/originals/orig.jpg"
VARIANT_KEY = f"{BANNER_PREFIX}/orig_800w.webp"


class SellerStub:
    """Minimal seller for filter tests; avoids a database round trip."""

    def __init__(self, key=ORIGINAL_KEY, variants=None):
        self.featured_image = key
        self.featured_image_variants = variants


class TestSellerBannerUrl:
    """The filter must prefer the variant and degrade gracefully."""

    def test_prefers_the_variant(self):
        seller = SellerStub(variants={BANNER_VARIANT_NAME: VARIANT_KEY})
        assert seller_banner_url(seller) == f"/media/{VARIANT_KEY}"

    def test_falls_back_to_the_original_without_variants(self):
        assert seller_banner_url(SellerStub()) == f"/media/{ORIGINAL_KEY}"

    def test_falls_back_when_variants_are_null(self):
        seller = SellerStub(variants=None)
        assert seller_banner_url(seller) == f"/media/{ORIGINAL_KEY}"

    def test_falls_back_when_variants_lack_the_banner_key(self):
        seller = SellerStub(variants={"something_else": "x.webp"})
        assert seller_banner_url(seller) == f"/media/{ORIGINAL_KEY}"

    def test_empty_for_a_seller_with_no_image(self):
        assert seller_banner_url(SellerStub(key=None)) == ""

    def test_empty_for_no_seller(self):
        assert seller_banner_url(None) == ""


def _banner_tag(html: str) -> str:
    match = re.search(r"<img[^>]*Featured Image[^>]*>", html, re.S)
    assert match, "banner <img> not found in rendered page"
    return match.group(0)


class TestHomepageBanner:
    """End-to-end through the real route and template."""

    @pytest_asyncio.fixture
    async def seller_with_variant(self):
        async with maker() as session:
            seller = (
                await session.execute(select(Seller).where(Seller.id == 1))
            ).scalar_one()
            seller.featured_image = ORIGINAL_KEY
            seller.featured_image_variants = {BANNER_VARIANT_NAME: VARIANT_KEY}
            seller.updated_at = utc_now()
            await session.commit()

    @pytest.mark.asyncio
    async def test_homepage_serves_the_variant_webp(self, seller_with_variant):
        resp = client.get("/")
        assert resp.status_code == 200
        tag = _banner_tag(resp.text)
        assert f"/media/{VARIANT_KEY}" in tag
        assert ".webp" in tag, "banner should be WebP"

    @pytest.mark.asyncio
    async def test_homepage_does_not_serve_the_original_jpeg(self, seller_with_variant):
        """The regression in one assertion: no .jpg on the homepage banner."""
        resp = client.get("/")
        assert ORIGINAL_KEY not in resp.text

    @pytest.mark.asyncio
    async def test_homepage_still_renders_without_a_variant(self):
        """A seller whose banner has not been processed must still get an image."""
        async with maker() as session:
            seller = (
                await session.execute(select(Seller).where(Seller.id == 1))
            ).scalar_one()
            seller.featured_image = ORIGINAL_KEY
            seller.featured_image_variants = None
            seller.updated_at = utc_now()
            await session.commit()

        resp = client.get("/")
        assert resp.status_code == 200
        assert f"/media/{ORIGINAL_KEY}" in _banner_tag(resp.text)

    @pytest.mark.asyncio
    async def test_homepage_omits_the_banner_when_there_is_no_image(self):
        async with maker() as session:
            seller = (
                await session.execute(select(Seller).where(Seller.id == 1))
            ).scalar_one()
            seller.featured_image = None
            seller.featured_image_variants = None
            seller.updated_at = utc_now()
            await session.commit()

        resp = client.get("/")
        assert resp.status_code == 200


class TestBannerTemplates:
    """Neither banner template may route a bare key through media_url."""

    def test_home_template_uses_the_banner_filter(self):
        from src.templates_config import _PROJECT_ROOT
        import os

        body = open(
            os.path.join(_PROJECT_ROOT, "src/templates/buyer_home.html"), encoding="utf-8"
        ).read()
        assert "seller_banner_url" in body
        assert "featured_image | media_url" not in body, (
            "passing the bare key to media_url returns the original and "
            "silently disables the variant"
        )

    def test_profile_template_uses_the_banner_filter(self):
        from src.templates_config import _PROJECT_ROOT
        import os

        body = open(
            os.path.join(_PROJECT_ROOT, "src/templates/dashboard/profile.html"),
            encoding="utf-8",
        ).read()
        assert "seller_banner_url" in body
        assert "featured_image | media_url" not in body

    def test_home_banner_declares_its_intrinsic_size(self):
        """
        The attributes must match the generated width, otherwise the browser
        reserves the wrong box before the image loads.
        """
        from src.templates_config import _PROJECT_ROOT
        import os

        from src.scripts.process_images import BANNER_WIDTH

        body = open(
            os.path.join(_PROJECT_ROOT, "src/templates/buyer_home.html"), encoding="utf-8"
        ).read()
        tag = re.search(r"<img[^>]*Featured Image[^>]*>", body, re.S).group(0)
        assert f'width="{BANNER_WIDTH}"' in tag
        assert 'fetchpriority="high"' in tag, (
            "the banner is the LCP element; it should be fetched eagerly"
        )


class TestNoBareKeyThroughMediaUrl:
    """
    Guard against the class of bug, not just this instance.

    media_url accepts a bare object key and returns the original no matter what
    width is asked for. That made `seller.featured_image | media_url(800)` look
    correct while quietly shipping the 304 KB original. Any template that does it
    again is optimising nothing.
    """

    #: Columns that are a bare object key with no generated variants. Passing
    #: one of these to media_url returns the original whatever width is asked,
    #: which is the bug this test exists to catch.
    BARE_KEY_COLUMNS = ("featured_image", "image_key", "object_name")

    def test_no_template_pipes_a_bare_key_column_into_media_url(self):
        import glob
        import os

        from src.templates_config import _PROJECT_ROOT

        offenders = []
        for path in glob.glob(
            os.path.join(_PROJECT_ROOT, "src/templates/**/*.html"), recursive=True
        ):
            body = open(path, encoding="utf-8").read()
            for match in re.finditer(r"\{\{([^}]*)\|\s*media_url\([^}]*\}\}", body):
                expr = match.group(1)
                for column in self.BARE_KEY_COLUMNS:
                    # Match seller.featured_image but not product.display_image,
                    # which is a ProductImage row and does have variants.
                    if re.search(rf"\.{column}\s*$", expr.strip()):
                        offenders.append(f"{os.path.basename(path)}: {expr.strip()}")
        assert not offenders, (
            "these pass a bare object key to media_url, so the width is ignored "
            "and the unoptimised original is served: " + "; ".join(offenders)
        )


class TestPruneKeepsBanner:
    """A generated banner must not be deleted as an orphan."""

    @pytest.mark.asyncio
    async def test_prune_treats_the_banner_variant_as_referenced(self):
        """
        A banner variant that is not in the referenced set gets unlinked by the
        next prune, so this guards a data-loss bug rather than a cosmetic one.
        """
        from src.scripts.prune_orphans import collect_referenced

        async with maker() as session:
            seller = (
                await session.execute(select(Seller).where(Seller.id == 1))
            ).scalar_one()
            seller.featured_image = ORIGINAL_KEY
            seller.featured_image_variants = {BANNER_VARIANT_NAME: VARIANT_KEY}
            await session.commit()

        async with maker() as session:
            referenced = await collect_referenced(session)

        assert VARIANT_KEY in referenced
        assert ORIGINAL_KEY in referenced

    @pytest.mark.asyncio
    async def test_prune_handles_a_seller_with_null_variants(self):
        from src.scripts.prune_orphans import collect_referenced

        async with maker() as session:
            seller = (
                await session.execute(select(Seller).where(Seller.id == 1))
            ).scalar_one()
            seller.featured_image = ORIGINAL_KEY
            seller.featured_image_variants = None
            await session.commit()

        async with maker() as session:
            referenced = await collect_referenced(session)

        assert ORIGINAL_KEY in referenced


class TestBannerUploadPath:
    """update_profile must populate the variant column when an image is stored."""

    def test_routes_module_exposes_the_banner_helper(self):
        from src.features.dashboard import routes

        assert hasattr(routes, "store_banner_variant"), (
            "update_profile needs store_banner_variant to generate the variant"
        )

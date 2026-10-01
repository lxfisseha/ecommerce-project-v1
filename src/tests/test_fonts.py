"""
Guards on the webfont wiring.

Two bugs motivated these, both invisible at runtime:

1. Every @font-face src carried `?v=1` while no <link rel="preload"> did. Those
   are different cache keys, so the browser could not match a preload to its
   font request and downloaded each preloaded font twice. The wasted copy also
   competed for bandwidth, which is what made the hero font flip between reloads.
2. Anton SC was `font-display: optional`, which permits a ~100ms block period
   and then never swaps, so a slow first visit kept the fallback font for the
   whole page view and a reload changed which font rendered.

These assert on the built output.css and the templates that reference it, since
those are what actually ship.
"""
import os
import re

import pytest

from src.templates_config import _PROJECT_ROOT, templates

INPUT_CSS = os.path.join(_PROJECT_ROOT, "src/static/css/input.css")
OUTPUT_CSS = os.path.join(_PROJECT_ROOT, "src/static/css/output.css")
BASE_HTML = os.path.join(_PROJECT_ROOT, "src/templates/base.html")
HOME_HTML = os.path.join(_PROJECT_ROOT, "src/templates/buyer_home.html")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def input_css() -> str:
    return read(INPUT_CSS)


@pytest.fixture(scope="module")
def output_css() -> str:
    return read(OUTPUT_CSS)


def font_src_urls(css: str) -> set[str]:
    """
    Local font URLs referenced by an @font-face src, for both CSS dialects.

    input.css is hand-written, so its url() is quoted:
        src: url('/static/fonts/inter-latin.woff2') format('woff2');
    output.css is minified, so the same value loses its quotes:
        src:url(/static/fonts/inter-latin.woff2)format("woff2")

    A strict unquoted pattern silently finds nothing in the quoted form, which
    made these guards pass vacuously, so both spellings are matched explicitly.
    """
    urls = set()
    for match in re.findall(r"url\(\s*['\"]?(/static/fonts/[^)'\"]+)['\"]?\s*\)", css):
        urls.add(match)
    return urls


def preload_hrefs(*template_paths: str) -> set[str]:
    hrefs = set()
    for path in template_paths:
        body = read(path)
        for tag in re.findall(r"<link[^>]*rel=\"preload\"[^>]*>", body):
            match = re.search(r'href="([^"]+)"', tag)
            if match and "/static/fonts/" in match.group(1):
                hrefs.add(match.group(1))
    return hrefs


class TestNoQueryStringMismatch:
    """
    A preload only helps if its href is byte-identical to the @font-face src.

    Anything else is a separate cache key, so the font is fetched twice and the
    preload is pure waste.
    """

    def test_font_urls_carry_no_query_string(self, input_css):
        offenders = [
            url for url in font_src_urls(input_css) if "?" in url or "#" in url
        ]
        assert not offenders, (
            "these @font-face srcs carry a query or fragment, so they will not "
            f"match a plain preload href: {offenders}"
        )

    def test_built_css_carries_no_query_string(self, output_css):
        offenders = [url for url in font_src_urls(output_css) if "?" in url]
        assert not offenders, (
            f"output.css still has versioned font URLs: {offenders}. Rebuild "
            "with `npm run build:css` after changing input.css."
        )

    def test_every_preloaded_font_is_used_by_a_font_face(self):
        """
        Catches the inverse drift too: a preload for a file no @font-face
        references would download a font nothing can use.
        """
        css_urls = font_src_urls(read(INPUT_CSS))
        orphaned = preload_hrefs(BASE_HTML, HOME_HTML) - css_urls
        assert not orphaned, f"preloaded but never referenced by @font-face: {orphaned}"

    def test_each_preloaded_font_matches_a_font_face_exactly(self):
        """
        The regression itself, asserted directly rather than inferred.
        """
        css_urls = font_src_urls(read(INPUT_CSS))
        for href in preload_hrefs(BASE_HTML, HOME_HTML):
            assert href in css_urls, (
                f'preload href "{href}" is not a @font-face src, so the browser '
                "will download the font twice"
            )

    def test_preloaded_fonts_declare_crossorigin(self):
        """
        Font fetches are CORS-mode even same-origin. Without crossorigin the
        preload is fetched in a different mode and discarded, so it never
        satisfies the font request.
        """
        for path in (BASE_HTML, HOME_HTML):
            for tag in re.findall(r"<link[^>]*rel=\"preload\"[^>]*>", read(path)):
                if "/static/fonts/" in tag:
                    assert "crossorigin" in tag, (
                        f"font preload in {os.path.basename(path)} lacks "
                        "crossorigin and will be thrown away"
                    )


class TestAntonIsNotOptional:
    """
    `optional` never swaps after its block period, so the hero's typeface
    depends on whether Anton SC beat ~100ms on that particular load. A reload
    changing the rendered font is that race landing differently.
    """

    ANTON_FACE = re.compile(
        r"@font-face\s*\{[^}]*font-family:\s*'Anton SC'[^}]*\}", re.S
    )

    def test_anton_face_exists(self, input_css):
        assert self.ANTON_FACE.search(input_css), "Anton SC @font-face not found"

    def test_anton_uses_swap(self, input_css):
        face = self.ANTON_FACE.search(input_css).group(0)
        assert "font-display: swap" in face, (
            "Anton SC must use font-display: swap; optional silently keeps the "
            "fallback for the whole page view on a slow load"
        )

    def test_no_font_face_uses_optional(self, input_css):
        """
        Guard the class rather than the instance. `optional` is a deliberate
        choice for genuinely decorative faces; it was wrong here because this one
        carries the LCP headline.
        """
        assert "font-display: optional" not in input_css, (
            "font-display: optional makes the rendered face depend on network "
            "timing, which shows up as a different font on reload"
        )


class TestMetricMatchedFallback:
    """
    A fallback with Anton's metrics reserves the right space, so swapping the
    webfont in does not reflow the hero.
    """

    def test_anton_fallback_face_exists(self, input_css):
        assert "@font-face" in input_css and "AntonFallback" in input_css

    def test_fallback_declares_the_overrides(self, input_css):
        face = re.search(
            r"@font-face\s*\{[^}]*font-family:\s*'AntonFallback'[^}]*\}",
            input_css,
            re.S,
        )
        assert face, "AntonFallback @font-face not found"
        body = face.group(0)
        for prop in ("size-adjust", "ascent-override", "descent-override"):
            assert prop in body, f"{prop} missing from AntonFallback"

    def test_fallback_makes_no_network_request(self, input_css):
        """
        The whole point of the metric match is to avoid a download, so a src url
        here would defeat it and cost another round trip.
        """
        face = re.search(
            r"@font-face\s*\{[^}]*font-family:\s*'AntonFallback'[^}]*\}",
            input_css,
            re.S,
        ).group(0)
        assert "/static/fonts/" not in face, (
            "AntonFallback must resolve via local(), not fetch a file"
        )
        assert "local(" in face

    def test_display_stack_includes_the_fallback(self):
        """A declared face the font stack never names is dead CSS."""
        config = read(os.path.join(_PROJECT_ROOT, "tailwind.config.js"))
        display = re.search(r"display:\s*\[(.*?)\]", config, re.S)
        assert display, "display font stack not found in tailwind.config.js"
        stack = display.group(1)
        assert "Anton SC" in stack
        assert "AntonFallback" in stack
        # Fallback order must be webfont, then metric match, then the real
        # fallback. Getting this wrong swaps in the metric match permanently.
        assert stack.index("Anton SC") < stack.index("AntonFallback") < stack.index("Inter")

    def test_built_css_keeps_the_metric_overrides(self, output_css):
        """
        Guards against output.css being stale after an input.css change, which
        would ship the old fonts while the source looks correct.
        """
        assert "size-adjust:134.168%" in output_css, (
            "output.css lacks the AntonFallback metrics; rebuild with "
            "`npm run build:css`"
        )


class TestUnusedSubsetsRemoved:
    """
    The -latin-ext subsets covered accented Latin, Vietnamese and Turkish. The
    catalogue is English and Amharic, and Amharic (U+1200-137F) is in neither
    subset, so both were fetched and never matched a glyph: 117 KB wasted.
    """

    def test_latin_ext_faces_are_gone(self, input_css):
        assert "inter-latin-ext" not in input_css
        assert "anton-sc-latin-ext" not in input_css

    def test_built_css_has_no_latin_ext(self, output_css):
        assert "latin-ext" not in output_css

    def test_one_face_per_network_font(self, output_css):
        """
        One face per downloadable family. A second face for the same family is
        a second file fetched.

        Counted inside @font-face blocks only: the minified utility class
        .font-display also spells the family name, and matching it would make
        this count 2 for a perfectly correct stylesheet.

        AntonFallback is expected here but must resolve through local(), which
        test_fallback_makes_no_network_request asserts.
        """
        faces = re.findall(r"@font-face\{([^}]*)\}", output_css)
        assert faces, "no @font-face blocks found in output.css"

        network_families = []
        for block in faces:
            family = re.search(r"font-family:([\w ]+?)(?:;|$)", block)
            family = family.group(1).strip() if family else "?"
            network_families.append(family)
            if family != "AntonFallback":
                assert "/static/fonts/" in block, (
                    f"{family} has no src url, so it cannot render"
                )
                assert "url(" in block, (
                    f"{family} does not reference a file; only AntonFallback "
                    "may resolve via local()"
                )

        assert sorted(network_families) == ["Anton SC", "AntonFallback", "Inter"]


class TestRenderedPages:
    """End-to-end: what the browser actually receives."""

    @staticmethod
    def _rendered(path: str, ctx: dict) -> str:
        return templates.env.get_template(path).render(csrf_token="t", **ctx)

    def test_homepage_preloads_resolve_to_a_font_face(self):
        """
        The page inlines output.css, so the assertions that hold for the file on
        disk must also hold for the copy the browser parses.
        """
        from starlette.requests import Request

        from test_fonts_support import SellerStub, make_request

        html = self._rendered("buyer_home.html", {
            "request": make_request("/"),
            "seller": SellerStub(),
        })

        inlined = font_src_urls(html)
        assert inlined, "no font URLs inlined in the homepage"
        assert not [u for u in inlined if "?" in u], (
            f"inlined CSS still has versioned font URLs: {inlined}"
        )

        for href in re.findall(
            r'<link[^>]*rel="preload"[^>]*href="(/static/fonts/[^"]+)"', html
        ):
            assert href in inlined, (
                f'homepage preloads "{href}" but the inlined CSS has no '
                "@font-face for it, so the browser downloads the font twice"
            )

    def test_shop_page_preloads_resolve_to_a_font_face(self):
        from test_fonts_support import make_request

        html = self._rendered("buyer_shop.html", {
            "request": make_request("/shop"),
            "products": [],
            "current_page": 1,
            "total_pages": 1,
        })

        inlined = font_src_urls(html)
        assert inlined, "no font URLs inlined on the shop page"
        for href in re.findall(
            r'<link[^>]*rel="preload"[^>]*href="(/static/fonts/[^"]+)"', html
        ):
            assert href in inlined, (
                f'shop preloads "{href}" with no matching @font-face: {inlined}'
            )

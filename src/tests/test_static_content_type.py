"""
Static asset content types.

Starlette derives the content type from mimetypes, whose database is empty in
the slim container, so self-hosted woff2 was served as
application/octet-stream. Browsers that enforce the strict font MIME policy
reject a font served under that type and fall back to a system face for the
whole page view, which is indistinguishable from a font that failed to download.

These mirror test_media_content_type.py, which covers the /media mount.
"""
import os
import tempfile

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from src.main import CachedStaticFiles

# FileResponse only stats and labels the file; the bytes need not be a real font.
WOFF2_BYTES = b"wOF2" + b"\x00" * 12


def _client(files: dict[str, bytes]) -> TestClient:
    tmpdir = tempfile.mkdtemp()
    for name, data in files.items():
        with open(os.path.join(tmpdir, name), "wb") as handle:
            handle.write(data)

    app = Starlette(routes=[
        Mount("/static", CachedStaticFiles(directory=tmpdir)),
    ])
    return TestClient(app)


class TestFontContentType:
    def test_woff2_is_served_as_font_woff2(self):
        client = _client({"inter.woff2": WOFF2_BYTES})
        r = client.get("/static/inter.woff2")
        assert r.status_code == 200
        assert r.headers["content-type"] == "font/woff2"

    def test_exactly_one_content_type_header(self):
        """
        A duplicated Content-Type is a real failure mode: browsers read the
        first value, so a stale application/octet-stream ahead of the correct
        one defeats the fix while looking correct in a header dump.
        """
        client = _client({"inter.woff2": WOFF2_BYTES})
        values = client.get("/static/inter.woff2").headers.get_list("content-type")
        assert len(values) == 1, f"expected one content-type, got {values}"

    def test_woff_is_typed(self):
        client = _client({"legacy.woff": b"\x00" * 16})
        assert client.get("/static/legacy.woff").headers["content-type"] == "font/woff"

    def test_webp_is_typed(self):
        client = _client({"img.webp": b"RIFF" + b"\x00" * 12})
        assert client.get("/static/img.webp").headers["content-type"] == "image/webp"


class TestStaticCaching:
    def test_fonts_are_cached_immutably(self):
        """
        The font URLs carry no ?v= query any more, so immutable caching rests on
        this alone. Without it a font change would be invisible until a hard
        reload, which is the reason the query string existed in the first place.
        """
        client = _client({"inter.woff2": WOFF2_BYTES})
        cc = client.get("/static/inter.woff2").headers["cache-control"]
        assert "immutable" in cc
        assert "31536000" in cc

    def test_other_assets_still_cached_immutably(self):
        client = _client({"app.js": b"console.log(1)"})
        assert "immutable" in client.get("/static/app.js").headers["cache-control"]


class TestOrdinaryFormatsUnaffected:
    """The override table must not shadow types the host resolves correctly."""

    def test_css_still_resolves(self):
        client = _client({"app.css": b"body{}"})
        assert "css" in client.get("/static/app.css").headers["content-type"]

    def test_missing_file_is_404(self):
        assert _client({}).get("/static/nope.woff2").status_code == 404

    def test_svg_is_image_svg(self):
        client = _client({"icon.svg": b"<svg/>"})
        assert client.get("/static/icon.svg").headers["content-type"] == "image/svg+xml"

import os
import tempfile

import pytest
from starlette.testclient import TestClient

from src.main import MediaFiles

# A lossy WebP header is enough: FileResponse only stats and labels the file,
# it never decodes the image.
WEBP_BYTES = b"RIFF" + (12).to_bytes(4, "little") + b"WEBP" + b"VP8 " + b"\x00" * 8


def _client(files: dict[str, bytes]) -> TestClient:
    """Mount MediaFiles the way main.py does, so 404s surface as responses
    rather than raised HTTPExceptions."""
    from starlette.applications import Starlette
    from starlette.routing import Mount

    tmpdir = tempfile.mkdtemp()
    for name, data in files.items():
        with open(os.path.join(tmpdir, name), "wb") as fh:
            fh.write(data)

    app = Starlette(routes=[Mount("/media", MediaFiles(directory=tmpdir))])
    return TestClient(app)


class TestMediaContentType:

    def test_webp_is_served_as_image_webp(self):
        # Slim containers ship no mimetypes database, so the default response
        # for a generated variant would be application/octet-stream.
        client = _client({"variant.webp": WEBP_BYTES})
        r = client.get("/media/variant.webp")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/webp"

    @pytest.mark.parametrize("ext", ["avif", "heic", "heif", "jpe", "tif", "tiff"])
    def test_other_generated_formats_are_typed(self, ext):
        client = _client({f"img.{ext}": b"x" * 16})
        assert client.get(f"/media/img.{ext}").headers["content-type"].startswith("image/")

    def test_ordinary_formats_still_resolve(self):
        client = _client({"photo.jpg": b"x" * 16, "icon.svg": b"<svg/>"})
        assert client.get("/media/photo.jpg").headers["content-type"] == "image/jpeg"
        assert "svg" in client.get("/media/icon.svg").headers["content-type"]

    def test_media_is_cached_immutably(self):
        client = _client({"variant.webp": WEBP_BYTES})
        cc = client.get("/media/variant.webp").headers["cache-control"]
        assert "immutable" in cc
        assert "31536000" in cc

    def test_missing_file_is_404(self):
        assert _client({}).get("/media/nope.webp").status_code == 404

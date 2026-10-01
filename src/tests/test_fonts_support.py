"""Shared fixtures for the font rendering tests."""
from starlette.requests import Request


class SellerStub:
    def __init__(self, key="sellers/1/featured/originals/a.jpg", variants=None):
        self.featured_image = key
        self.featured_image_variants = variants or {
            "banner": "processed/sellers/a_800w.webp"
        }
        self.store_name = "Test Store"


def make_request(path: str = "/") -> Request:
    return Request({
        "type": "http", "method": "GET", "path": path,
        "headers": [], "query_string": b"", "scheme": "http",
        "server": ("x", 80), "client": ("x", 1),
    })

from functools import lru_cache
import os

from fastapi.templating import Jinja2Templates
from fastapi import Request
from markupsafe import Markup


def csrf_token_context_processor(request: Request):
    return {"csrf_token": request.scope.get("csrf_token")}


def cart_count_context_processor(request: Request):
    from src.features.buyer.services import CartService

    return {"cart_count": CartService.count(request)}


def cloudinary_url(url: str, width: int = 0, height: int = 0, quality: str = "auto:eco") -> str:
    parts = url.split("/upload/")
    if len(parts) != 2:
        return url
    transforms = f"f_auto,q_{quality}"
    if width:
        transforms += f",w_{width}"
    if height:
        transforms += f",h_{height},c_fill"
    return f"{parts[0]}/upload/{transforms}/{parts[1]}"


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache(maxsize=1)
def _read_inline_css(rel_path: str) -> str:
    """Read a CSS file (cached) so it can be inlined to avoid render-blocking requests."""
    full = os.path.normpath(os.path.join(_PROJECT_ROOT, rel_path))
    try:
        with open(full, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def inline_css(rel_path: str) -> Markup:
    return Markup(_read_inline_css(rel_path))


templates = Jinja2Templates(
    directory="src/templates",
    context_processors=[csrf_token_context_processor, cart_count_context_processor]
)
templates.env.filters["cloudinary"] = cloudinary_url
templates.env.filters["inline_css"] = inline_css

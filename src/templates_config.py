from fastapi.templating import Jinja2Templates
from fastapi import Request


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


templates = Jinja2Templates(
    directory="src/templates",
    context_processors=[csrf_token_context_processor, cart_count_context_processor]
)
templates.env.filters["cloudinary"] = cloudinary_url

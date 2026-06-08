from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_session
from src.templates_config import templates
from src.features.auth.models import Seller
from sqlmodel import select

router = APIRouter()


@router.get("/")
async def get_dashboard(request: Request, db: AsyncSession = Depends(get_session)):
    seller_id = request.session.get("seller_id")
    if not seller_id:
        return RedirectResponse(url="/auth/login")
    # Lookup seller to show friendly name
    result = await db.execute(select(Seller).where(Seller.id == int(seller_id)))
    seller = result.scalar_one_or_none()
    if not seller:
        # If seller not found, redirect to login
        return RedirectResponse(url="/auth/login")

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name,
        },
    )

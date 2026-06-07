from fastapi import APIRouter, Request, Depends, HTTPException
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
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/auth/login")

    # Fetch seller name
    statement = select(Seller).where(Seller.id == seller_id)
    result = await db.execute(statement)
    seller = result.scalar_one_or_none()

    if not seller:
        request.session.clear()
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/auth/login")

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name
        },
    )

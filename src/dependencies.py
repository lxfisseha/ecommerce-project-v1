from fastapi import Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.database import get_session
from src.features.auth.models import Seller


async def get_current_seller_id(request: Request) -> int | None:
    """Extract seller_id from session. Returns None if not logged in."""
    return request.session.get("seller_id")


async def get_current_seller(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> Seller | None:
    """Fetch the current seller from DB. Returns None if not logged in."""
    seller_id = request.session.get("seller_id")
    if not seller_id:
        return None
    result = await db.execute(select(Seller).where(Seller.id == seller_id))
    return result.scalar_one_or_none()


async def require_seller_id(
    seller_id: int | None = Depends(get_current_seller_id),
) -> int:
    """Require an authenticated seller. Raises 303 redirect if not logged in."""
    if not seller_id:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return seller_id


async def require_current_seller(
    seller: Seller | None = Depends(get_current_seller),
) -> Seller:
    """Require an authenticated seller with DB record. Raises 303 redirect if not."""
    if not seller:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return seller

from typing import List, Optional
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.features.products.models import Product

class BuyerProductService:
    @staticmethod
    async def get_all_active_products(db: AsyncSession, search: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Product]:
        """
        Retrieves all active and in-stock products for buyers.
        Eagerly loads images and attributes. Supports searching by name or description.
        """
        statement = (
            select(Product)
            .where(Product.in_stock == True)
            .options(selectinload(Product.images), selectinload(Product.attributes))
            .offset(offset)
            .limit(limit)
            .order_by(Product.created_at.desc())
        )

        if search:
            search_filter = f"%{search}%"
            statement = statement.where(
                (Product.name.ilike(search_filter)) | 
                (Product.description.ilike(search_filter))
            )

        result = await db.execute(statement)
        return result.scalars().unique().all()

    @staticmethod
    async def get_product_by_id(db: AsyncSession, product_id: int) -> Optional[Product]:
        """
        Retrieves a single product by ID, ensuring it is active and in-stock.
        Eagerly loads images, attributes, and seller.
        """
        statement = (
            select(Product)
            .where(Product.id == product_id, Product.in_stock == True)
            .options(
                selectinload(Product.images), 
                selectinload(Product.attributes),
                selectinload(Product.seller)
            )
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

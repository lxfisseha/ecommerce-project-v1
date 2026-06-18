from typing import List, Optional, Tuple
from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.features.products.models import Product

class BuyerProductService:
    @staticmethod
    async def get_all_active_products(
        db: AsyncSession, 
        search: Optional[str] = None, 
        sort_by: Optional[str] = None,
        limit: int = 100, 
        offset: int = 0
    ) -> Tuple[List[Product], int]:
        """
        Retrieves active products and the total count for pagination.
        Supports searching and sorting.
        """
        # Base query for products
        query = select(Product).where(Product.in_stock == True)
        
        # Base query for total count
        count_query = select(func.count(Product.id)).where(Product.in_stock == True)

        # Apply Search to both queries
        if search:
            search_filter = f"%{search}%"
            query = query.where(
                (Product.name.ilike(search_filter)) | 
                (Product.description.ilike(search_filter))
            )
            count_query = count_query.where(
                (Product.name.ilike(search_filter)) | 
                (Product.description.ilike(search_filter))
            )

        # Apply Sorting to product query only
        if sort_by == "price-low":
            query = query.order_by(Product.price.asc())
        elif sort_by == "price-high":
            query = query.order_by(Product.price.desc())
        elif sort_by == "popular":
            # Temporary placeholder for popularity: sort by ID to show a different order than newest
            query = query.order_by(Product.id.asc())
        else:
            # Default to newest
            query = query.order_by(Product.created_at.desc())

        # Get total count
        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0

        # Execute product query with limit/offset
        query = query.offset(offset).limit(limit).options(selectinload(Product.images), selectinload(Product.attributes))
        result = await db.execute(query)
        products = result.scalars().unique().all()
        
        return products, total_count

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

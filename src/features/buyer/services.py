from typing import List, Optional, Tuple
from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.features.products.models import Product, Tag, ProductTagLink

class BuyerProductService:
    @staticmethod
    async def get_all_active_products(
        db: AsyncSession, 
        search: Optional[str] = None, 
        sort_by: Optional[str] = None,
        tag_slug: Optional[str] = None,
        limit: int = 100, 
        offset: int = 0
    ) -> Tuple[List[Product], int]:
        """
        Retrieves active products and the total count for pagination.
        Supports searching (including tag keywords), tag filtering, and sorting.
        """
        # Base query for products
        query = select(Product).where(Product.in_stock == True).where(Product.is_deleted == False)
        
        # Base query for total count
        count_query = select(func.count(Product.id)).where(Product.in_stock == True).where(Product.is_deleted == False)

        # Apply Tag Slug filtering if provided
        if tag_slug:
            tag_filter_exists = select(ProductTagLink).join(Tag, ProductTagLink.tag_id == Tag.id).where(
                (ProductTagLink.product_id == Product.id) & (Tag.slug == tag_slug)
            ).exists()
            query = query.where(tag_filter_exists)
            count_query = count_query.where(tag_filter_exists)

        # Apply Search to both queries (including tag keyword search)
        if search:
            search_filter = f"%{search}%"
            # Subquery to check if any associated tags match the search term
            tag_exists = select(ProductTagLink).join(Tag, ProductTagLink.tag_id == Tag.id).where(
                (ProductTagLink.product_id == Product.id) & (Tag.name.ilike(search_filter))
            ).exists()

            query = query.where(
                (Product.name.ilike(search_filter)) | 
                (Product.description.ilike(search_filter)) |
                tag_exists
            )
            count_query = count_query.where(
                (Product.name.ilike(search_filter)) | 
                (Product.description.ilike(search_filter)) |
                tag_exists
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
        query = query.offset(offset).limit(limit).options(
            selectinload(Product.images), 
            selectinload(Product.attributes),
            selectinload(Product.tags)
        )
        result = await db.execute(query)
        products = result.scalars().unique().all()
        
        return products, total_count

    @staticmethod
    async def get_product_by_id(db: AsyncSession, product_id: int) -> Optional[Product]:
        """
        Retrieves a single product by ID, ensuring it is active and in-stock.
        Eagerly loads images, attributes, tags, and seller.
        """
        statement = (
            select(Product)
            .where(Product.id == product_id, Product.in_stock == True, Product.is_deleted == False)
            .options(
                selectinload(Product.images), 
                selectinload(Product.attributes),
                selectinload(Product.tags),
                selectinload(Product.seller)
            )
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_active_tags(db: AsyncSession) -> List[Tag]:
        """
        Retrieves all tags that are associated with at least one active, non-deleted product.
        """
        statement = (
            select(Tag)
            .join(ProductTagLink, ProductTagLink.tag_id == Tag.id)
            .join(Product, ProductTagLink.product_id == Product.id)
            .where(Product.in_stock == True)
            .where(Product.is_deleted == False)
            .distinct()
            .order_by(Tag.name.asc())
        )
        result = await db.execute(statement)
        return result.scalars().all()

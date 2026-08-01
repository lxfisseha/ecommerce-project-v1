from typing import List, Optional, Tuple
from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import Request
from src.features.products.models import Product, Tag, ProductTagLink

MAX_CART_ITEMS = 20
MIN_CART_QTY = 1
MAX_CART_QTY = 100


class CartService:
    """
    Session-cookie backed cart for anonymous buyers.
    Stores only product ids, quantities and attribute strings — prices and
    stock are always re-fetched from the DB when the cart is rendered.
    """
    CART_KEY = "cart"

    @staticmethod
    def _get_items(request: Request) -> List[dict]:
        cart = request.session.get(CartService.CART_KEY)
        items = cart.get("items") if isinstance(cart, dict) else None
        if not isinstance(items, list):
            return []
        return [i for i in items if isinstance(i, dict)]

    @staticmethod
    def _save(request: Request, items: List[dict]) -> None:
        request.session[CartService.CART_KEY] = {"items": items}

    @staticmethod
    def get_cart(request: Request) -> List[dict]:
        return CartService._get_items(request)

    @staticmethod
    def count(request: Request) -> int:
        return sum(int(i.get("qty", 0)) for i in CartService._get_items(request))

    @staticmethod
    def add(
        request: Request, product_id: int, qty: int, attributes: Optional[str] = None
    ) -> int:
        items = CartService._get_items(request)
        qty = max(MIN_CART_QTY, min(MAX_CART_QTY, qty))
        attrs = (attributes or "").strip()

        for item in items:
            if item.get("product_id") == product_id and (item.get("attrs") or "") == attrs:
                item["qty"] = min(MAX_CART_QTY, int(item.get("qty", 0)) + qty)
                CartService._save(request, items)
                return CartService.count(request)

        if len(items) < MAX_CART_ITEMS:
            items.append({"product_id": product_id, "qty": qty, "attrs": attrs})
        CartService._save(request, items)
        return CartService.count(request)

    @staticmethod
    def update_qty(request: Request, index: int, qty: int) -> None:
        items = CartService._get_items(request)
        if 0 <= index < len(items):
            items[index]["qty"] = max(MIN_CART_QTY, min(MAX_CART_QTY, qty))
            CartService._save(request, items)

    @staticmethod
    def remove(request: Request, index: int) -> None:
        items = CartService._get_items(request)
        if 0 <= index < len(items):
            items.pop(index)
            CartService._save(request, items)

    @staticmethod
    def clear(request: Request) -> None:
        request.session.pop(CartService.CART_KEY, None)

class BuyerProductService:
    @staticmethod
    async def get_all_active_products(
        db: AsyncSession, 
        search: Optional[str] = None, 
        sort_by: Optional[str] = None,
        tag_slug: Optional[str] = None,
        limit: int = 100, 
        offset: int = 0,
        include_count: bool = True
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
        if include_count:
            count_result = await db.execute(count_query)
            total_count = count_result.scalar() or 0
        else:
            total_count = 0

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
    async def get_products_by_ids(db: AsyncSession, ids: List[int]) -> List[Product]:
        """
        Fetches multiple active, non-deleted products in a single query with
        their images, attributes, tags, and seller eagerly loaded. Used by the
        cart to avoid one query per line item.
        """
        if not ids:
            return []
        statement = (
            select(Product)
            .where(
                Product.id.in_(ids),
                Product.in_stock == True,
                Product.is_deleted == False,
            )
            .options(
                selectinload(Product.images),
                selectinload(Product.attributes),
                selectinload(Product.tags),
                selectinload(Product.seller),
            )
        )
        result = await db.execute(statement)
        return result.scalars().unique().all()

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

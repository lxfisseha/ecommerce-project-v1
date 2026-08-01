from typing import List, Optional, Tuple
from sqlmodel import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import anyio
from decimal import Decimal
from .models import Product, ProductImage, ProductAttribute, ProductTagLink, Tag

class ProductService:
    @staticmethod
    async def update_product_attributes(
        db: AsyncSession,
        product_id: int,
        attributes: List[dict] # List of {"type": "Color", "value": "Red", "extra_price": 0.0}
    ):
        """
        Clears existing attributes and adds new ones.
        """
        product = await ProductService.get_product_by_id(db, product_id)
        if not product:
            return

        # Clear existing attributes - cascade="all, delete-orphan" will handle deletion
        product.attributes.clear()

        # Add new
        for attr_data in attributes:
            new_attr = ProductAttribute(
                product_id=product_id,
                attribute_type=attr_data["type"],
                attribute_value=attr_data["value"],
                extra_price=Decimal(str(attr_data.get("extra_price", 0.0)))
            )
            product.attributes.append(new_attr)
        
        db.add(product)
        await db.flush()

    @staticmethod
    async def sync_product_tags(
        db: AsyncSession,
        product: Product,
        tags_string: str
    ):
        # Ensure product.tags is loaded to prevent lazy-loading in async context
        if "tags" not in product.__dict__:
            await db.execute(
                select(Product).where(Product.id == product.id).options(selectinload(Product.tags))
            )

        # Split and clean the tags
        tag_names = [t.strip() for t in tags_string.split(",") if t.strip()]
        
        # Unique list of cleaned tag names
        seen_tags = {}
        for name in tag_names:
            cleaned_name = name.lower()
            if cleaned_name not in seen_tags:
                seen_tags[cleaned_name] = name

        # If there are no tags requested, clear tags relationship
        if not seen_tags:
            product.tags.clear()
            db.add(product)
            await db.flush()
            return

        # Fetch existing tags in one batched query, then create only the missing ones
        slugs = {name.replace(" ", "-").replace("/", "-") for name in seen_tags}
        existing = {}
        if slugs:
            result = await db.execute(select(Tag).where(Tag.slug.in_(slugs)))
            existing = {t.slug: t for t in result.scalars().all()}

        db_tags = []
        for cleaned_name, orig_name in seen_tags.items():
            slug = cleaned_name.replace(" ", "-").replace("/", "-")
            db_tag = existing.get(slug)
            if db_tag is None:
                db_tag = Tag(name=orig_name, slug=slug)
                db.add(db_tag)
            db_tags.append(db_tag)

        if any(t.id is None for t in db_tags):
            await db.flush()

        # Sync the tags on the product
        product.tags = db_tags
        db.add(product)
        await db.flush()

    @staticmethod
    async def get_all_products(db: AsyncSession) -> List[Product]:
        statement = (
            select(Product)
            .where(Product.is_deleted == False)
            .options(selectinload(Product.images), selectinload(Product.attributes), selectinload(Product.tags))
            .order_by(Product.created_at.desc())
        )
        result = await db.execute(statement)
        return result.scalars().all()

    @staticmethod
    async def get_product_by_id(db: AsyncSession, product_id: int) -> Optional[Product]:
        statement = (
            select(Product)
            .where(Product.id == product_id)
            .where(Product.is_deleted == False)
            .options(selectinload(Product.images), selectinload(Product.attributes), selectinload(Product.tags))
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_product(
        db: AsyncSession, 
        seller_id: int, 
        name: str, 
        description: str, 
        price: float, 
        in_stock: bool
    ) -> Product:
        if price <= 0:
            raise ValueError("Price must be greater than zero.")

        product = Product(
            seller_id=seller_id,
            name=name,
            description=description,
            price=price,
            in_stock=in_stock
        )
        db.add(product)
        await db.flush()
        
        # Re-fetch with relationships
        return await ProductService.get_product_by_id(db, product.id)

    @staticmethod
    async def update_product(
        db: AsyncSession,
        product_id: int,
        **kwargs
    ) -> Optional[Product]:
        if "price" in kwargs and kwargs["price"] <= 0:
            raise ValueError("Price must be greater than zero.")

        product = await ProductService.get_product_by_id(db, product_id)
        if not product:
            return None
        
        for key, value in kwargs.items():
            if hasattr(product, key):
                setattr(product, key, value)
        
        db.add(product)
        await db.flush()
        
        # Re-fetch with relationships
        return await ProductService.get_product_by_id(db, product.id)

    @staticmethod
    async def delete_product(db: AsyncSession, product_id: int) -> bool:
        product = await ProductService.get_product_by_id(db, product_id)
        if not product:
            return False

        # Delete Cloudinary images before soft-deleting
        from src.utils.storage import CloudinaryService
        for image in product.images:
            if image.image_url:
                try:
                    await anyio.to_thread.run_sync(
                        lambda: CloudinaryService.delete_image(image.image_url)
                    )
                except Exception:
                    pass  # Best-effort cleanup

        product.is_deleted = True
        db.add(product)
        await db.commit()
        return True

    @staticmethod
    async def search_products(db: AsyncSession, query: str) -> List[Product]:
        search = f"%{query}%"
        tag_exists = select(ProductTagLink).join(Tag, ProductTagLink.tag_id == Tag.id).where(
            (ProductTagLink.product_id == Product.id) & (Tag.name.ilike(search))
        ).exists()
        statement = (
            select(Product)
            .where(Product.is_deleted == False)
            .where(
                (Product.name.ilike(search)) |
                (Product.description.ilike(search)) |
                tag_exists
            )
            .options(selectinload(Product.images), selectinload(Product.attributes), selectinload(Product.tags))
            .order_by(Product.created_at.desc())
        )
        result = await db.execute(statement)
        return result.scalars().all()

    @staticmethod
    async def get_products_paginated(db: AsyncSession, limit: int = 12, offset: int = 0) -> Tuple[List[Product], int]:
        count_statement = select(func.count(Product.id)).where(Product.is_deleted == False)
        count_result = await db.execute(count_statement)
        total_count = count_result.scalar() or 0

        statement = (
            select(Product)
            .where(Product.is_deleted == False)
            .options(selectinload(Product.images), selectinload(Product.attributes), selectinload(Product.tags))
            .order_by(Product.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(statement)
        return result.scalars().all(), total_count

    @staticmethod
    async def search_products_paginated(db: AsyncSession, query: str, limit: int = 12, offset: int = 0) -> Tuple[List[Product], int]:
        search = f"%{query}%"
        tag_exists = select(ProductTagLink).join(Tag, ProductTagLink.tag_id == Tag.id).where(
            (ProductTagLink.product_id == Product.id) & (Tag.name.ilike(search))
        ).exists()

        count_statement = select(func.count(Product.id)).where(Product.is_deleted == False).where(
            (Product.name.ilike(search)) |
            (Product.description.ilike(search)) |
            tag_exists
        )
        count_result = await db.execute(count_statement)
        total_count = count_result.scalar() or 0

        statement = (
            select(Product)
            .where(Product.is_deleted == False)
            .where(
                (Product.name.ilike(search)) |
                (Product.description.ilike(search)) |
                tag_exists
            )
            .options(selectinload(Product.images), selectinload(Product.attributes), selectinload(Product.tags))
            .order_by(Product.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(statement)
        return result.scalars().all(), total_count

    @staticmethod
    async def add_attribute(
        db: AsyncSession, 
        product_id: int, 
        attr_type: str, 
        attr_value: str, 
        extra_price: float = 0.0
    ) -> ProductAttribute:
        attr = ProductAttribute(
            product_id=product_id,
            attribute_type=attr_type,
            attribute_value=attr_value,
            extra_price=extra_price
        )
        db.add(attr)
        await db.commit()
        return attr

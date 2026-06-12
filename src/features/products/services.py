from typing import List, Optional
from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from .models import Product, ProductImage, ProductAttribute

class ProductService:
    @staticmethod
    async def update_product_attributes(
        db: AsyncSession,
        product_id: int,
        attributes: List[dict] # List of {"type": "Color", "value": "Red"}
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
                attribute_value=attr_data["value"]
            )
            product.attributes.append(new_attr)
        
        db.add(product)
        await db.flush()

    @staticmethod
    async def get_seller_products(db: AsyncSession, seller_id: int) -> List[Product]:
        statement = (
            select(Product)
            .where(Product.seller_id == seller_id)
            .options(selectinload(Product.images), selectinload(Product.attributes))
            .order_by(Product.created_at.desc())
        )
        result = await db.execute(statement)
        return result.scalars().all()

    @staticmethod
    async def get_product_by_id(db: AsyncSession, product_id: int) -> Optional[Product]:
        statement = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.images), selectinload(Product.attributes))
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
        await db.commit()
        
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
        await db.commit()
        
        # Re-fetch with relationships
        return await ProductService.get_product_by_id(db, product.id)

    @staticmethod
    async def delete_product(db: AsyncSession, product_id: int) -> bool:
        product = await ProductService.get_product_by_id(db, product_id)
        if not product:
            return False
        
        await db.delete(product)
        await db.commit()
        return True

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
        await db.refresh(attr)
        return attr

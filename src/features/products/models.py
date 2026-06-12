from src.utils.datetime import utc_now
from datetime import datetime
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from decimal import Decimal

class Product(SQLModel, table=True):
    __tablename__ = "products"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    seller_id: int = Field(foreign_key="sellers.id", index=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None)
    price: Decimal = Field(default=0.0, decimal_places=2, gt=0)
    in_stock: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    images: List["ProductImage"] = Relationship(back_populates="product", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    attributes: List["ProductAttribute"] = Relationship(back_populates="product", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class ProductImage(SQLModel, table=True):
    __tablename__ = "product_images"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="products.id", index=True)
    image_url: str
    image_tag: str = Field(default="gallery", max_length=20) # main, thumbnail, gallery
    display_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now)

    product: Product = Relationship(back_populates="images")

class ProductAttribute(SQLModel, table=True):
    __tablename__ = "product_attributes"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="products.id", index=True)
    attribute_type: str = Field(max_length=20) # e.g., Color, Size
    attribute_value: str = Field(max_length=50)
    extra_price: Decimal = Field(default=0.0, decimal_places=2)
    created_at: datetime = Field(default_factory=utc_now)

    product: Product = Relationship(back_populates="attributes")

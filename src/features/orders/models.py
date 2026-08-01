from datetime import datetime
from typing import Optional, List
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel, Relationship
from decimal import Decimal
from src.utils.datetime import utc_now


class OrderItem(SQLModel, table=True):
    __tablename__ = "order_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", index=True)
    product_id: int = Field(foreign_key="products.id")
    product_name: str = Field(max_length=200)
    product_price: Decimal = Field(decimal_places=2)
    quantity: int = Field(default=1)
    attributes_selected: Optional[str] = Field(default=None)  # JSON or Comma-separated
    subtotal: Decimal = Field(decimal_places=2)

    order: "Order" = Relationship(back_populates="items")


class Order(SQLModel, table=True):
    __tablename__ = "orders"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(index=True, unique=True, max_length=50)  # ET-[prefix]-[YYYYMMDD]-[0001]
    seller_id: int = Field(foreign_key="sellers.id", index=True)

    buyer_name: str = Field(max_length=100)
    buyer_phone: str = Field(max_length=512)  # AES-256 Encrypted
    buyer_phone_hash: str = Field(index=True, max_length=256)  # HMAC-SHA256 for lookup
    delivery_address: str = Field(max_length=1024)  # AES-256 Encrypted
    delivery_address_hash: Optional[str] = Field(default=None, max_length=256)  # Optional lookup

    subtotal: Decimal = Field(decimal_places=2)
    delivery_fee: Decimal = Field(default=Decimal("150.00"), decimal_places=2)
    total_amount: Decimal = Field(decimal_places=2)

    status: str = Field(default="pending", index=True, max_length=20)  # pending, shipped, completed, cancelled
    status_updated_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)

    items: List["OrderItem"] = Relationship(
        back_populates="order", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class OrderSequence(SQLModel, table=True):
    __tablename__ = "order_sequences"
    __table_args__ = (UniqueConstraint("store_prefix", "date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    store_prefix: str = Field(max_length=10)
    date: str = Field(max_length=8)  # YYYYMMDD
    seq: int = Field(default=0)


class OrderStatusLog(SQLModel, table=True):
    __tablename__ = "order_status_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", index=True)
    old_status: Optional[str] = Field(default=None, max_length=20)
    new_status: str = Field(max_length=20)
    changed_by: str = Field(max_length=50)  # e.g., 'seller' or 'system'
    changed_at: datetime = Field(default_factory=utc_now, index=True)
    context: Optional[str] = Field(default=None, max_length=500)  # Additional details

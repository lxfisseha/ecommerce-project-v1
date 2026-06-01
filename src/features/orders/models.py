from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel
from decimal import Decimal

class Order(SQLModel, table=True):
    __tablename__ = "orders"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(index=True, unique=True, max_length=50) # ET-[prefix]-[YYYYMMDD]-[0001]
    seller_id: int = Field(foreign_key="sellers.id", index=True)
    
    buyer_name: str = Field(max_length=100)
    buyer_phone: str = Field(index=True, max_length=15)
    delivery_address: str
    
    product_id: int = Field(foreign_key="products.id")
    product_name: str = Field(max_length=200)
    product_price: Decimal = Field(decimal_places=2)
    quantity: int = Field(default=1)
    
    attributes_selected: Optional[str] = Field(default=None) # JSON or Comma-separated
    subtotal: Decimal = Field(decimal_places=2)
    total_amount: Decimal = Field(decimal_places=2)
    
    status: str = Field(default="pending", index=True, max_length=20) # pending, shipped, completed, cancelled
    status_updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class OrderStatusLog(SQLModel, table=True):
    __tablename__ = "order_status_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", index=True)
    old_status: Optional[str] = Field(default=None, max_length=20)
    new_status: str = Field(max_length=20)
    changed_by: str = Field(max_length=50) # e.g., 'seller' or 'system'
    changed_at: datetime = Field(default_factory=datetime.utcnow, index=True)

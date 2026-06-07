from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel

class Seller(SQLModel, table=True):
    __tablename__ = "sellers"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    first_name: str = Field(max_length=50)
    last_name: str = Field(max_length=50)
    store_name: str = Field(index=True, unique=True, max_length=100)
    store_prefix: str = Field(max_length=10, unique=True)  # Required for ET-[store prefix]-... format
    phone: str = Field(index=True, unique=True, max_length=15)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class OtpCode(SQLModel, table=True):
    __tablename__ = "otp_codes"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    phone: str = Field(index=True, max_length=15)
    code: str = Field(max_length=6)
    expires_at: datetime = Field(index=True)
    used: bool = Field(default=False)
    attempts: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)

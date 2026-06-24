from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel
from src.utils.datetime import utc_now

class Seller(SQLModel, table=True):
    __tablename__ = "sellers"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    first_name: str = Field(max_length=50)
    last_name: str = Field(max_length=50)
    store_name: str = Field(index=True, unique=True, max_length=100)
    store_prefix: str = Field(max_length=10, unique=True)  # Required for ET-[store prefix]-... format
    phone: str = Field(max_length=512) # AES-256 Encrypted
    phone_hash: str = Field(index=True, unique=True, max_length=256) # HMAC-SHA256 for lookup
    business_email: Optional[str] = Field(default=None, max_length=255)
    business_address: Optional[str] = Field(default=None, max_length=255)
    telegram_username: Optional[str] = Field(default=None, max_length=100)
    business_contact_number: Optional[str] = Field(default=None, max_length=10)
    featured_image: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

class OtpCode(SQLModel, table=True):
    __tablename__ = "otp_codes"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    phone: str = Field(max_length=512) # AES-256 Encrypted
    phone_hash: str = Field(index=True, max_length=256) # HMAC-SHA256 for lookup
    code: str = Field(max_length=6)
    expires_at: datetime = Field(index=True)
    used: bool = Field(default=False)
    attempts: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from .config import settings

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=settings.DATABASE_ECHO,
    future=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Create session factory
async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        # Import all models here so SQLModel knows about them
        from .features.auth.models import Seller, OtpCode
        from .features.products.models import Product, ProductImage, ProductAttribute, Tag, ProductTagLink
        from .features.orders.models import Order, OrderStatusLog
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session

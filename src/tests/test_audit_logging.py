import pytest
import pytest_asyncio
from src.features.orders.models import Order, OrderStatusLog
from src.features.orders.services import OrderService
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from src.features.auth.models import Seller
from src.features.products.models import Product
from src.utils.crypto import encrypt_phone, hash_phone
from decimal import Decimal

# Setup async sqlite for testing (mirroring existing test structure)
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@pytest_asyncio.fixture
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with async_session_maker() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

@pytest.mark.asyncio
async def test_order_audit_logging_flow(db_session: AsyncSession):
    """
    Verify that creating an order and updating its status correctly creates audit logs.
    """
    # 1. Setup a minimal seller and product
    phone_raw = "912345678"
    seller = Seller(
        id=1, first_name="T", last_name="U", store_name="TS", store_prefix="TS",
        phone=encrypt_phone(phone_raw), phone_hash=hash_phone(phone_raw)
    )
    product = Product(
        id=1, seller_id=1, name="TP", description="TD", price=Decimal("100.00"), in_stock=True
    )
    db_session.add(seller)
    db_session.add(product)
    await db_session.commit()

    # Create order
    order = await OrderService.create_order(
        db_session, product, "Buyer", "0911111111", "Addr", 1
    )
    
    # 2. Verify initial log (created during create_order)
    logs_stmt = select(OrderStatusLog).where(OrderStatusLog.order_id == order.id).order_by(OrderStatusLog.changed_at)
    logs = (await db_session.execute(logs_stmt)).scalars().all()
    
    assert len(logs) == 1
    assert logs[0].new_status == "pending"
    assert logs[0].changed_by == "system"
    assert logs[0].context == "Order created"

    # 3. Update status and verify log creation
    new_context = "Buyer confirmed shipping"
    await OrderService.update_order_status(db_session, order.id, "shipped", changed_by="seller", context=new_context)
    
    # 4. Verify logs after update
    logs = (await db_session.execute(logs_stmt)).scalars().all()
    assert len(logs) == 2
    assert logs[1].old_status == "pending"
    assert logs[1].new_status == "shipped"
    assert logs[1].changed_by == "seller"
    assert logs[1].context == new_context

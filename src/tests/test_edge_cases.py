import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from src.main import app
from src.database import get_session
from src.features.auth.models import Seller, OtpCode
from src.features.products.models import Product
from src.features.orders.models import Order
from src.features.orders.services import OrderService
from src.utils.crypto import encrypt_phone, hash_phone, encrypt_data, hash_data, decrypt_data
from src.utils.datetime import utc_now
from decimal import Decimal
from datetime import timedelta

# Setup async sqlite for testing
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def override_get_session():
    async with async_session_maker() as session:
        yield session

@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    app.dependency_overrides[get_session] = override_get_session
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    async with async_session_maker() as session:
        # Create Seller A
        phone_a = "911111111"
        seller_a = Seller(
            id=1,
            first_name="Seller",
            last_name="A",
            store_name="Store A",
            store_prefix="STOA",
            phone=encrypt_phone(phone_a),
            phone_hash=hash_phone(phone_a)
        )
        # Create Seller B
        phone_b = "922222222"
        seller_b = Seller(
            id=2,
            first_name="Seller",
            last_name="B",
            store_name="Store B",
            store_prefix="STOB",
            phone=encrypt_phone(phone_b),
            phone_hash=hash_phone(phone_b)
        )
        # Create Product A for Seller A
        product_a = Product(
            id=10,
            seller_id=1,
            name="Product A",
            price=Decimal("100.00"),
            in_stock=True
        )
        session.add_all([seller_a, seller_b, product_a])
        await session.commit()
    
    yield
    
    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

@pytest.mark.asyncio
async def test_unauthorized_dashboard_redirect(client):
    response = await client.get("/dashboard", follow_redirects=False)
    if response.status_code in [302, 307] and response.headers["location"].endswith("/dashboard/"):
        response = await client.get(response.headers["location"], follow_redirects=False)

    assert response.status_code in [302, 307]
    assert response.headers["location"].endswith("/auth/login")

@pytest.mark.asyncio
async def test_unauthorized_product_management_fails(client):
    response = await client.get("/dashboard/products")
    assert response.status_code in [401, 302, 307]

@pytest.mark.asyncio
async def test_cross_seller_protection(client):
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 2
    
    response = await client.get("/dashboard/products/edit/10")
    assert response.status_code == 404
    
    # Get token
    await client.get("/auth/login")
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None
    
    response = await client.delete(
        "/dashboard/products/10",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_invalid_phone_format_login(client):
    await client.get("/auth/login")
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    # Too short
    response = await client.post(
        "/auth/login", 
        data={"phone": "911", "csrf_token": csrf_token}, 
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 422
    
    # Wrong prefix
    response = await client.post(
        "/auth/login", 
        data={"phone": "0811111111", "csrf_token": csrf_token}, 
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 422
    
    # Non-numeric
    response = await client.post(
        "/auth/login", 
        data={"phone": "911abcdefg", "csrf_token": csrf_token}, 
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_otp_expiry_enforcement():
    async with async_session_maker() as session:
        # Create an expired OTP
        phone = "911111111"
        otp = OtpCode(
            phone=encrypt_phone(phone),
            phone_hash=hash_phone(phone),
            code="123456",
            expires_at=utc_now() - timedelta(minutes=1), # Expired
            used=False
        )
        session.add(otp)
        await session.commit()
        
        from src.features.auth.services import AuthService
        result = await AuthService.verify_otp(session, phone, "123456")
        assert result["success"] is False
        assert "expired" in result["message"].lower()

@pytest.mark.asyncio
async def test_otp_attempt_limit_enforcement():
    async with async_session_maker() as session:
        phone = "911111111"
        # Create OTP already at 3 attempts
        otp = OtpCode(
            phone=encrypt_phone(phone),
            phone_hash=hash_phone(phone),
            code="123456",
            expires_at=utc_now() + timedelta(minutes=5),
            used=False,
            attempts=3
        )
        session.add(otp)
        await session.commit()
        
        from src.features.auth.services import AuthService
        # Even with correct code, it should fail
        result = await AuthService.verify_otp(session, phone, "123456")
        assert result["success"] is False
        assert "too many attempts" in result["message"].lower()

@pytest.mark.asyncio
async def test_order_terminal_state_lock():
    async with async_session_maker() as session:
        # Create a completed order
        order = Order(
            order_id="ET-LOCK-0001",
            seller_id=1,
            buyer_name="Buyer",
            buyer_phone="ENC_P",
            buyer_phone_hash="HASH_P",
            delivery_address="ENC_A",
            product_id=10,
            product_name="Product A",
            product_price=Decimal("100"),
            quantity=1,
            subtotal=Decimal("100"),
            total_amount=Decimal("250"),
            status="completed"
        )
        session.add(order)
        await session.commit()
        
        # Attempt to move back to shipped
        with pytest.raises(ValueError, match="terminal state"):
            await OrderService.update_order_status(session, order.id, "shipped")

@pytest.mark.asyncio
async def test_encryption_integrity_in_db():
    async with async_session_maker() as session:
        # Create order via service
        product_a = await session.get(Product, 10)
        raw_phone = "0911111111"
        raw_address = "Bole Road"
        
        order = await OrderService.create_order(
            session,
            product=product_a,
            buyer_name="Test Buyer",
            buyer_phone=raw_phone,
            delivery_address=raw_address,
            quantity=1
        )
        
        # Check raw database values
        from sqlalchemy import text
        result = await session.execute(text(f"SELECT buyer_phone, delivery_address FROM orders WHERE id = {order.id}"))
        row = result.fetchone()
        
        db_phone = row[0]
        db_address = row[1]
        
        # Verify it's NOT plain text
        assert db_phone != raw_phone
        assert db_address != raw_address
        
        # Verify it's decryptable to the original
        assert decrypt_data(db_phone) == raw_phone
        assert decrypt_data(db_address) == raw_address

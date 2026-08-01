import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlmodel import select
from src.main import app
from src.features.auth.models import Seller, OtpCode
from src.features.products.models import Product
from src.features.orders.models import Order
from src.features.orders.services import OrderService
from src.utils.crypto import encrypt_phone, hash_phone, decrypt_data
from src.utils.datetime import utc_now
from decimal import Decimal
from datetime import timedelta
from src.tests.conftest import maker


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def seed_extra_data():
    """Add extra seller (id=2) and product (id=10) beyond conftest's default seller."""
    async with maker() as session:
        seller_b = Seller(
            id=2, first_name="Seller", last_name="B", store_name="Store B", store_prefix="STOB",
            phone=encrypt_phone("922222222"), phone_hash=hash_phone("922222222")
        )
        product_a = Product(
            id=10, seller_id=1, name="Product A", price=Decimal("100.00"), in_stock=True
        )
        session.add_all([seller_b, product_a])
        await session.commit()


@pytest.mark.asyncio
async def test_unauthorized_dashboard_redirect(client):
    response = await client.get("/dashboard", follow_redirects=False)
    if response.status_code in [302, 307] and response.headers["location"].endswith("/dashboard/"):
        response = await client.get(response.headers["location"], follow_redirects=False)
        assert response.status_code in [302, 307, 303]
    assert response.headers["location"].endswith("/auth/login")


@pytest.mark.asyncio
async def test_unauthorized_product_management_fails(client):
    response = await client.get("/dashboard/products")
    assert response.status_code in [401, 302, 307]


@pytest.mark.asyncio
async def test_invalid_phone_format_login(client):
    await client.get("/auth/login")
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    response = await client.post(
        "/auth/login",
        data={"phone": "911", "csrf_token": csrf_token},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 422

    response = await client.post(
        "/auth/login",
        data={"phone": "0811111111", "csrf_token": csrf_token},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 422

    response = await client.post(
        "/auth/login",
        data={"phone": "911abcdefg", "csrf_token": csrf_token},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_otp_expiry_enforcement():
    async with maker() as session:
        phone = "911111111"
        otp = OtpCode(
            phone=encrypt_phone(phone),
            phone_hash=hash_phone(phone),
            code="123456",
            expires_at=utc_now() - timedelta(minutes=1),
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
    async with maker() as session:
        phone = "911111111"
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
        result = await AuthService.verify_otp(session, phone, "123456")
        assert result["success"] is False
        assert "too many attempts" in result["message"].lower()


@pytest.mark.asyncio
async def test_order_terminal_state_lock():
    async with maker() as session:
        order = Order(
            order_id="ET-LOCK-0001",
            seller_id=1,
            buyer_name="Buyer",
            buyer_phone="ENC_P",
            buyer_phone_hash="HASH_P",
            delivery_address="ENC_A",
            subtotal=Decimal("100"),
            delivery_fee=Decimal("150.00"),
            total_amount=Decimal("250"),
            status="completed"
        )
        session.add(order)
        await session.commit()

        with pytest.raises(ValueError, match="terminal state"):
            await OrderService.update_order_status(session, order.id, "shipped")


@pytest.mark.asyncio
async def test_encryption_integrity_in_db():
    async with maker() as session:
        product_a = await session.get(Product, 10)
        raw_phone = "0911111111"
        raw_address = "Bole Road"

        order = await OrderService.create_order(
            session,
            product=product_a,
            buyer_name="Test Buyer",
            buyer_phone=raw_phone,
            delivery_address=raw_address,
            quantity=1,
            store_prefix="TEST"
        )

        from sqlalchemy import text
        result = await session.execute(text(f"SELECT buyer_phone, delivery_address FROM orders WHERE id = {order.id}"))
        row = result.fetchone()
        db_phone = row[0]
        db_address = row[1]

        assert db_phone != raw_phone
        assert db_address != raw_address
        assert decrypt_data(db_phone) == "911111111"
        assert decrypt_data(db_address) == raw_address

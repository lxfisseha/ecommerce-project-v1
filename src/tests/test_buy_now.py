import pytest
import pytest_asyncio
import re
from fastapi.testclient import TestClient
from src.main import app
from src.features.auth.models import Seller
from src.features.products.models import Product, ProductAttribute
from src.features.orders.models import Order
from src.features.orders.services import OrderService
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.database import get_session
from src.utils.datetime import utc_now
from src.utils.crypto import (
    encrypt_phone,
    decrypt_data,
    hash_phone,
    encrypt_data,
    hash_data,
)
from decimal import Decimal
from datetime import datetime

# Setup async sqlite for testing
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_session():
    async with async_session_maker() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    app.dependency_overrides[get_session] = override_get_session
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session_maker() as session:
        phone_raw = "912345678"
        seller = Seller(
            id=1,
            first_name="Test",
            last_name="User",
            store_name="Test Store",
            store_prefix="TEST",
            phone=encrypt_phone(phone_raw),
            phone_hash=hash_phone(phone_raw),
        )
        product = Product(
            id=1,
            seller_id=1,
            name="Test Product",
            description="Test Description",
            price=1000.0,
            in_stock=True,
        )
        session.add(seller)
        session.add(product)
        await session.commit()

    yield

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest.mark.asyncio
async def test_order_id_generation():
    async with async_session_maker() as session:
        order_id = await OrderService.generate_order_id(session, 1)
        # Format: ET-TEST-[YYYYMMDD]-0001
        assert order_id.startswith("ET-TEST-")
        assert order_id.endswith("-0001")

        # Add an order and check next sequence
        order = Order(
            order_id=order_id,
            seller_id=1,
            buyer_name="B1",
            buyer_phone="ENC_P1",
            buyer_phone_hash="HASH_P1",
            delivery_address="ENC_A1",
            delivery_address_hash="HASH_A1",
            product_id=1,
            product_name="P1",
            product_price=100,
            quantity=1,
            subtotal=100,
            total_amount=250,
            created_at=utc_now(),
            status_updated_at=utc_now(),
        )
        session.add(order)
        await session.commit()

        next_id = await OrderService.generate_order_id(session, 1)
        assert next_id.endswith("-0002")


@pytest.mark.asyncio
async def test_order_creation_service_encryption():
    async with async_session_maker() as session:
        product = await session.get(Product, 1)
        raw_phone = "0911223344"
        raw_address = "Bole, Addis Ababa"

        order = await OrderService.create_order(
            session,
            product=product,
            buyer_name="Abebe",
            buyer_phone=raw_phone,
            delivery_address=raw_address,
            quantity=2,
            attributes_selected="Size: L",
        )

        # Check database directly - should be encrypted
        assert order.buyer_phone != raw_phone
        assert order.delivery_address != raw_address

        # Check decryption - should be normalized to 9 digits
        assert decrypt_data(order.buyer_phone) == "911223344"
        assert decrypt_data(order.delivery_address) == raw_address

        assert order.buyer_name == "Abebe"
        assert order.total_amount == Decimal("2150.00")  # 2000 + 150 fee


@pytest.mark.asyncio
async def test_order_creation_service_includes_attribute_extra_price():
    async with async_session_maker() as session:
        product = await session.get(Product, 1)
        attr = ProductAttribute(
            product_id=product.id,
            attribute_type="Color",
            attribute_value="Red",
            extra_price=Decimal("100.00"),
        )
        session.add(attr)
        await session.commit()

        order = await OrderService.create_order(
            session,
            product=product,
            buyer_name="Abebe",
            buyer_phone="0911223344",
            delivery_address="Bole, Addis Ababa",
            quantity=2,
            attributes_selected="Color: Red",
        )

        assert order.subtotal == Decimal("2200.00")
        assert order.total_amount == Decimal("2350.00")


@pytest.mark.asyncio
async def test_checkout_page_get():
    client = TestClient(app)
    response = client.get("/checkout/1?qty=3&attrs=Size: XL")
    assert response.status_code == 200
    assert "Secure Checkout" in response.text
    assert "Test Product" in response.text
    assert "Qty: 3" in response.text
    assert "Size: XL" in response.text


@pytest.mark.asyncio
async def test_process_checkout_success():
    client = TestClient(app)

    # 1. GET to set the cookie and get token
    get_resp = client.get("/checkout/1")
    match = re.search(r'name="csrf_token" value="([^"]+)"', get_resp.text)
    token = match.group(1)

    raw_phone = "0911234567"
    data = {
        "buyer_name": "Abebe Kebede",
        "buyer_phone": raw_phone,
        "delivery_address": "Bole Sub-city",
        "quantity": "1",
        "attributes": "Color: Red",
        "csrf_token": token,
    }

    response = client.post(
        "/checkout/1",
        data=data,
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/order-confirmation/ET-TEST-")

    # Verify order in DB (should be encrypted)
    async with async_session_maker() as session:
        statement = select(Order).where(Order.buyer_name == "Abebe Kebede")
        result = await session.execute(statement)
        order = result.scalar_one_or_none()
        assert order is not None
        assert order.buyer_phone != raw_phone
        assert decrypt_data(order.buyer_phone) == "911234567"


@pytest.mark.asyncio
async def test_order_confirmation_decryption():
    # 1. Create order with encrypted data
    raw_phone = "0911111111"
    normalized_phone = "911111111"
    raw_address = "Addis Ababa"

    async with async_session_maker() as session:
        order = Order(
            order_id="ET-DECRYPT-20240101-0001",
            seller_id=1,
            buyer_name="Abebe",
            buyer_phone=encrypt_data(normalized_phone),
            buyer_phone_hash=hash_data(normalized_phone),
            delivery_address=encrypt_data(raw_address),
            delivery_address_hash=hash_data(raw_address),
            product_id=1,
            product_name="Test Product",
            product_price=1000,
            quantity=1,
            subtotal=1000,
            total_amount=1150,
            status="pending",
            created_at=utc_now(),
            status_updated_at=utc_now(),
        )
        session.add(order)
        await session.commit()

    client = TestClient(app)
    response = client.get("/order-confirmation/ET-DECRYPT-20240101-0001")
    assert response.status_code == 200
    assert "Order Confirmed" in response.text
    # Should be decrypted in HTML
    assert normalized_phone in response.text
    assert raw_address in response.text


@pytest.mark.asyncio
async def test_update_order_status_workflow():
    async with async_session_maker() as session:
        # Create initial order
        order = Order(
            order_id="ET-WORKFLOW-0001",
            seller_id=1,
            buyer_name="B1",
            buyer_phone="ENC_P1",
            buyer_phone_hash="HASH_P1",
            delivery_address="ENC_A1",
            delivery_address_hash="HASH_A1",
            product_id=1,
            product_name="P1",
            product_price=100,
            quantity=1,
            subtotal=100,
            total_amount=250,
            status="pending",
        )
        session.add(order)
        await session.commit()
        order_id = order.id

        # 1. Valid move: pending -> shipped
        updated = await OrderService.update_order_status(session, order_id, "shipped")
        assert updated.status == "shipped"

        # 2. Valid move: shipped -> completed
        updated = await OrderService.update_order_status(session, order_id, "completed")
        assert updated.status == "completed"

        # 3. Invalid move: completed -> pending (Terminal state lock FR18)
        with pytest.raises(ValueError, match="terminal state"):
            await OrderService.update_order_status(session, order_id, "pending")

        # 4. Invalid transition move (if we had more states or strict flow)
        # Re-create a pending order for testing invalid transitions
        order2 = Order(
            order_id="ET-WORKFLOW-0002",
            seller_id=1,
            buyer_name="B2",
            buyer_phone="P2",
            buyer_phone_hash="HASH_P2",
            delivery_address="A2",
            product_id=1,
            product_name="P1",
            product_price=100,
            quantity=1,
            subtotal=100,
            total_amount=250,
            status="pending",
        )
        session.add(order2)
        await session.commit()

        with pytest.raises(ValueError, match="Invalid transition"):
            # pending -> completed is NOT in our valid_transitions map (must go through shipped)
            await OrderService.update_order_status(session, order2.id, "completed")

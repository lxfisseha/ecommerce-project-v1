import pytest
import pytest_asyncio
import re
from fastapi.testclient import TestClient
from src.main import app
from src.features.auth.models import Seller
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.database import get_session
from src.utils.crypto import encrypt_phone, hash_phone
from unittest.mock import patch

# Setup async sqlite for testing
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def override_get_session():
    async with async_session_maker() as session:
        yield session

client = TestClient(app)

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
            phone_hash=hash_phone(phone_raw)
        )
        session.add(seller)
        await session.commit()

    yield

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest.mark.asyncio
async def test_get_profile_unauthenticated():
    """Unauthenticated users should be redirected to login."""
    response = client.get("/dashboard/profile", follow_redirects=False)
    assert response.status_code == 307


@pytest.mark.asyncio
async def test_get_profile_authenticated():
    """Authenticated user should see profile with seller data."""

    async def mock_get_current_seller(request, db):
        res = await db.execute(select(Seller).where(Seller.id == 1))
        return res.scalar_one_or_none()

    with patch("src.features.dashboard.routes.get_current_seller", side_effect=mock_get_current_seller):
        response = client.get("/dashboard/profile", follow_redirects=False)

    assert response.status_code == 200
    assert "Test" in response.text
    assert "User" in response.text
    assert "Test Store" in response.text


@pytest.mark.asyncio
async def test_post_profile_unauthenticated():
    """Unauthenticated POST should redirect to login."""
    response = client.post(
        "/dashboard/profile",
        data={"first_name": "Hacker", "last_name": "Bad", "store_name": "Hack Store"},
        follow_redirects=False
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_update_profile_basic_fields():
    """Test updating first name, last name, store name."""

    async def mock_get_current_seller(request, db):
        res = await db.execute(select(Seller).where(Seller.id == 1))
        return res.scalar_one_or_none()

    with patch("src.features.dashboard.routes.get_current_seller", side_effect=mock_get_current_seller):
        response = client.post(
            "/dashboard/profile",
            data={
                "first_name": "Updated",
                "last_name": "Name",
                "store_name": "Test Store",
            },
            follow_redirects=False
        )

    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text

    # Verify DB
    async with async_session_maker() as session:
        res = await session.execute(select(Seller).where(Seller.id == 1))
        seller = res.scalar_one_or_none()
        assert seller.first_name == "Updated"
        assert seller.last_name == "Name"


@pytest.mark.asyncio
async def test_update_profile_invalid_phone():
    """Business contact number must be a valid Ethiopian phone."""

    async def mock_get_current_seller(request, db):
        res = await db.execute(select(Seller).where(Seller.id == 1))
        return res.scalar_one_or_none()

    with patch("src.features.dashboard.routes.get_current_seller", side_effect=mock_get_current_seller):
        response = client.post(
            "/dashboard/profile",
            data={
                "first_name": "Test",
                "last_name": "User",
                "store_name": "Test Store",
                "business_contact_number": "12345",
            },
            follow_redirects=False
        )

    assert response.status_code == 200
    assert "Invalid business phone number" in response.text


@pytest.mark.asyncio
async def test_update_profile_duplicate_store_name():
    """Store name must be unique."""

    # Create a second seller
    async with async_session_maker() as session:
        seller2 = Seller(
            id=2,
            first_name="Other",
            last_name="Seller",
            store_name="Other Store",
            store_prefix="OTHR",
            phone=encrypt_phone("911111111"),
            phone_hash=hash_phone("911111111")
        )
        session.add(seller2)
        await session.commit()

    async def mock_get_current_seller(request, db):
        res = await db.execute(select(Seller).where(Seller.id == 1))
        return res.scalar_one_or_none()

    with patch("src.features.dashboard.routes.get_current_seller", side_effect=mock_get_current_seller):
        response = client.post(
            "/dashboard/profile",
            data={
                "first_name": "Test",
                "last_name": "User",
                "store_name": "Other Store",  # Already taken
            },
            follow_redirects=False
        )

    assert response.status_code == 200
    assert "Store name already exists" in response.text

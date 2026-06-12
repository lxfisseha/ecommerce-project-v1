import pytest
import pytest_asyncio
import re
from fastapi.testclient import TestClient
from src.main import app
from src.features.auth.models import Seller
from src.features.products.models import Product
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

async def get_csrf_context(client):
    response = client.get("/auth/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    token = match.group(1)
    csrf_cookie = response.cookies.get("csrftoken")
    return token, csrf_cookie

@pytest.mark.asyncio
async def test_add_product_size_too_large():
    token, csrf_cookie = await get_csrf_context(client)

    # Prepare file (6MB, exceeds 5MB limit)
    from io import BytesIO
    file_content = b"0" * (6 * 1024 * 1024)
    file = {"image": ("large.jpg", BytesIO(file_content), "image/jpeg")}

    data = {
        "name": "Large Product",
        "price": "100.50",
        "image_tag_0": "main",
        "csrf_token": token
    }
    
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    
    response = client.post(
        "/dashboard/products/add",
        data=data,
        files=file,
        cookies={"csrftoken": csrf_cookie},
        headers={"X-CSRF-Token": token}
    )
    
    assert response.status_code == 200
    assert "exceeds 5MB limit." in response.text

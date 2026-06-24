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
from io import BytesIO

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
    token = match.group(1) if match else ""
    csrf_cookie = response.cookies.get("csrftoken")
    return token, csrf_cookie

@pytest.mark.asyncio
async def test_update_profile_with_featured_image():
    token, csrf_cookie = await get_csrf_context(client)
    
    async def mock_get_current_seller(request, db):
        res = await db.execute(select(Seller).where(Seller.id == 1))
        return res.scalar_one_or_none()

    with patch("src.features.dashboard.routes.get_current_seller", side_effect=mock_get_current_seller):
        with patch("src.utils.storage.CloudinaryService.upload_image") as mock_upload:
            mock_upload.return_value = "http://cloudinary.com/featured_test.jpg"
            
            file_content = b"fake image content"
            file = {"featured_image": ("hero.jpg", BytesIO(file_content), "image/jpeg")}
            
            data = {
                "first_name": "Updated",
                "last_name": "Seller",
                "store_name": "Test Store",
                "csrf_token": token
            }
            
            response = client.post(
                "/dashboard/profile",
                data=data,
                files=file,
                cookies={"csrftoken": csrf_cookie},
                headers={"X-CSRF-Token": token},
                follow_redirects=False
            )
            
            assert response.status_code == 200
            assert "Profile updated successfully!" in response.text
            
            # Verify DB updated
            async with async_session_maker() as session:
                res = await session.execute(select(Seller).where(Seller.id == 1))
                seller = res.scalar_one_or_none()
                assert seller.first_name == "Updated"
                assert seller.featured_image == "http://cloudinary.com/featured_test.jpg"

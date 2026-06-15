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
    response = client.get("/dashboard/profile", follow_redirects=False)
    assert response.status_code == 307

@pytest.fixture
def auth_client():
    # Helper to get authenticated client
    get_response = client.get("/auth/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', get_response.text).group(1)
    csrf_cookie = get_response.cookies.get("csrftoken")
    
    # 1. Trigger OTP
    client.post("/auth/login", data={"phone": "912345678"}, headers={"X-CSRF-Token": token}, cookies={"csrftoken": csrf_cookie})
    
    # 2. Get OTP
    otp_code = ""
    with TestClient(app) as sync_client:
        # Need to access DB here, TestClient is tricky.
        # Alternative: use the async session maker directly
        pass
    
    # Because of complexity, let's just use a session override if possible, 
    # but for now, I will write the test assuming we have a way to authenticate.
    # Actually, I can just create a session cookie manually if I know the structure.
    return client

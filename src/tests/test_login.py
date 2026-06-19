import pytest
import pytest_asyncio
import re
from fastapi.testclient import TestClient
from src.main import app
from src.features.auth.models import Seller, OtpCode
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.database import get_session
from src.utils.crypto import encrypt_phone, hash_phone
from unittest.mock import patch, AsyncMock

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
async def test_login_csrf_header_missing():
    response = client.post("/auth/login", data={"phone": "912345678"})
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_login_success_and_otp_verify():
    # 1. GET to get the cookie and token
    get_response = client.get("/auth/login")
    assert get_response.status_code == 200
    
    match = re.search(r'name="csrf_token" value="([^"]+)"', get_response.text)
    assert match is not None
    token = match.group(1)
    csrf_cookie = get_response.cookies.get("csrftoken")
    
    # 2. POST login (OTP Generation)
    with patch("src.utils.sms.AfroMessageService.send_otp_sms", new_callable=AsyncMock, return_value=True):
        response = client.post(
            "/auth/login", 
            data={"phone": "912345678"},
            headers={"X-CSRF-Token": token},
            cookies={"csrftoken": csrf_cookie}
        )
    assert response.status_code == 200
    assert "Verify Number" in response.text
    
    # Check DB for OTP
    async with async_session_maker() as session:
        # We need to query using the hashed phone
        statement = select(OtpCode).where(OtpCode.phone_hash == hash_phone("912345678")).order_by(OtpCode.created_at.desc())
        result = await session.execute(statement)
        otp = result.scalar_one_or_none()
        assert otp is not None
        code = otp.code

    # 3. POST verify-otp
    verify_response = client.post(
        "/auth/verify-otp",
        data={"phone": "912345678", "code": code},
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": csrf_cookie, "session": response.cookies.get("session")}
    )
    assert verify_response.status_code == 200
    assert "HX-Redirect" in verify_response.headers

@pytest.mark.asyncio
async def test_login_invalid_phone():
    get_response = client.get("/auth/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', get_response.text).group(1)
    csrf_cookie = get_response.cookies.get("csrftoken")

    response = client.post(
        "/auth/login", 
        data={"phone": "12345"},
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": csrf_cookie}
    )
    assert response.status_code == 422
    assert "Invalid phone number" in response.text

@pytest.mark.asyncio
async def test_logout_success():
    response = client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"

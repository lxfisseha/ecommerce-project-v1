import os
import re
import tempfile
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from fastapi.testclient import TestClient
from src.main import app
from src.database import get_session
from src.features.auth.models import Seller
from src.utils.crypto import encrypt_phone, hash_phone

_db_file = os.path.join(tempfile.gettempdir(), f"test_{os.getpid()}.db")
SQLALCHEMY_DATABASE_URL = f"sqlite+aiosqlite:///{_db_file}"


def pytest_sessionfinish(session):
    import asyncio
    try:
        asyncio.run(engine.dispose())
    except Exception:
        pass
    try:
        if os.path.exists(_db_file):
            os.remove(_db_file)
    except PermissionError:
        pass


def get_csrf_token(client: TestClient) -> str:
    resp = client.get("/auth/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', resp.text)
    return match.group(1) if match else (client.cookies.get("csrftoken") or "")


def get_csrf_context(client: TestClient):
    resp = client.get("/auth/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', resp.text)
    token = match.group(1) if match else ""
    csrf_cookie = resp.cookies.get("csrftoken")
    return token, csrf_cookie


def setup_db_engine(url=SQLALCHEMY_DATABASE_URL):
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(url, connect_args={"check_same_thread": False})
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, maker


def override_get_session_from_maker(maker):
    async def _override():
        async with maker() as session:
            yield session
    return _override


def seed_seller(session, id=1, phone="912345678", name="Test", store="Test Store", prefix="TEST"):
    seller = Seller(
        id=id,
        first_name=name,
        last_name="User",
        store_name=store,
        store_prefix=prefix,
        phone=encrypt_phone(phone),
        phone_hash=hash_phone(phone)
    )
    session.add(seller)
    return seller


# --- Shared engine, sessionmaker, client (module-level, same pattern every test file already used) ---

engine, maker = setup_db_engine()

override_get_session = override_get_session_from_maker(maker)

client = TestClient(app)


@pytest_asyncio.fixture(autouse=True)
async def _db_setup_teardown():
    app.dependency_overrides[get_session] = override_get_session
    # Clear rate limiter in-memory store between tests
    _clear_rate_limiter(app)
    from src.features.dashboard.routes import _reset_dashboard_stats_cache
    _reset_dashboard_stats_cache()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    async with maker() as session:
        seed_seller(session)
        await session.commit()
    yield
    app.dependency_overrides.clear()
    _clear_rate_limiter(app)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


def _clear_rate_limiter(app_instance):
    """Walk the ASGI middleware stack and clear the rate limiter store."""
    stack = getattr(app_instance, 'middleware_stack', None)
    if not stack:
        return
    current = stack
    while current:
        if hasattr(current, '_store'):
            current._store.clear()
            if hasattr(current, '_req_count'):
                current._req_count = 0
            return
        current = getattr(current, 'app', None)


@pytest.fixture
def seller_id_override():
    from src.dependencies import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    yield
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest_asyncio.fixture
async def current_seller_override():
    """Override get_current_seller to return seller id=1 from the test DB."""
    from src.dependencies import get_current_seller
    async def _mock():
        async with maker() as session:
            res = await session.execute(select(Seller).where(Seller.id == 1))
            return res.scalar_one_or_none()
    app.dependency_overrides[get_current_seller] = _mock
    yield
    app.dependency_overrides.pop(get_current_seller, None)

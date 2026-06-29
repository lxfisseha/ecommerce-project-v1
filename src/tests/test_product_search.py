import pytest
import pytest_asyncio
import re
from fastapi.testclient import TestClient
from src.main import app
from src.features.auth.models import Seller
from src.features.products.models import Product, Tag
from src.features.products.services import ProductService
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload
from src.database import get_session
from src.utils.crypto import encrypt_phone, hash_phone

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

        p1 = Product(id=1, seller_id=1, name="Leather Wallet", description="Genuine leather bifold", price=500.0, in_stock=True)
        p2 = Product(id=2, seller_id=1, name="Cotton T-Shirt", description="100% organic cotton", price=300.0, in_stock=True)
        p3 = Product(id=3, seller_id=1, name="Leather Belt", description="Strong leather belt", price=250.0, in_stock=True)
        p4 = Product(id=4, seller_id=1, name="Deleted Item", description="Should not appear", price=10.0, in_stock=True, is_deleted=True)
        p5 = Product(id=5, seller_id=2, name="Other Seller Product", description="Not ours", price=99.0, in_stock=True)
        session.add_all([p1, p2, p3, p4, p5])
        await session.commit()
        await session.refresh(p1)
        await session.refresh(p2)
        await session.refresh(p3)

        await ProductService.sync_product_tags(session, p1, "accessories, leather")
        await ProductService.sync_product_tags(session, p2, "clothing, summer")
        await ProductService.sync_product_tags(session, p3, "accessories, leather")
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

# --- Service layer tests ---

@pytest.mark.asyncio
async def test_search_by_name():
    async with async_session_maker() as session:
        results = await ProductService.search_seller_products(session, 1, "Wallet")
        assert len(results) == 1
        assert results[0].name == "Leather Wallet"

@pytest.mark.asyncio
async def test_search_by_description():
    async with async_session_maker() as session:
        results = await ProductService.search_seller_products(session, 1, "organic")
        assert len(results) == 1
        assert results[0].name == "Cotton T-Shirt"

@pytest.mark.asyncio
async def test_search_by_tag_name():
    async with async_session_maker() as session:
        results = await ProductService.search_seller_products(session, 1, "summer")
        assert len(results) == 1
        assert results[0].name == "Cotton T-Shirt"

@pytest.mark.asyncio
async def test_search_multiple_results():
    async with async_session_maker() as session:
        results = await ProductService.search_seller_products(session, 1, "Leather")
        assert len(results) == 2
        names = [p.name for p in results]
        assert "Leather Wallet" in names
        assert "Leather Belt" in names

@pytest.mark.asyncio
async def test_search_case_insensitive():
    async with async_session_maker() as session:
        results = await ProductService.search_seller_products(session, 1, "WALLET")
        assert len(results) == 1
        assert results[0].name == "Leather Wallet"

@pytest.mark.asyncio
async def test_search_partial_match():
    async with async_session_maker() as session:
        results = await ProductService.search_seller_products(session, 1, "Wal")
        assert len(results) == 1
        assert results[0].name == "Leather Wallet"

@pytest.mark.asyncio
async def test_search_no_results():
    async with async_session_maker() as session:
        results = await ProductService.search_seller_products(session, 1, "NonexistentXYZ")
        assert len(results) == 0

@pytest.mark.asyncio
async def test_search_excludes_deleted_products():
    async with async_session_maker() as session:
        results = await ProductService.search_seller_products(session, 1, "Deleted")
        assert len(results) == 0

@pytest.mark.asyncio
async def test_search_only_own_seller_products():
    async with async_session_maker() as session:
        results = await ProductService.search_seller_products(session, 1, "Other Seller")
        assert len(results) == 0

@pytest.mark.asyncio
async def test_search_empty_query_returns_all():
    async with async_session_maker() as session:
        results = await ProductService.search_seller_products(session, 1, "")
        all_products = await ProductService.get_seller_products(session, 1)
        assert len(results) == len(all_products)

@pytest.mark.asyncio
async def test_search_special_characters():
    async with async_session_maker() as session:
        results = await ProductService.search_seller_products(session, 1, "%")
        assert isinstance(results, list)
        results = await ProductService.search_seller_products(session, 1, "'")
        assert isinstance(results, list)
        results = await ProductService.search_seller_products(session, 1, "*")
        assert isinstance(results, list)

# --- Route layer tests ---

@pytest.mark.asyncio
async def test_search_unauthenticated():
    response = client.get("/dashboard/products/?search=Leather", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"

@pytest.mark.asyncio
async def test_search_full_page():
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=Leather")
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Leather Belt" in response.text
    assert "Cotton T-Shirt" not in response.text
    assert "Product Management" in response.text
    assert "Add New Product" in response.text

@pytest.mark.asyncio
async def test_search_htmx_returns_partial():
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=Leather", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Leather Belt" in response.text
    assert "Cotton T-Shirt" not in response.text
    assert "Product Management" not in response.text
    assert 'id="product-list-content"' in response.text

@pytest.mark.asyncio
async def test_search_htmx_no_results():
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=NonexistentXYZ", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "No results found" in response.text
    assert "NonexistentXYZ" in response.text
    assert "Clear search" in response.text
    assert "Leather Wallet" not in response.text

@pytest.mark.asyncio
async def test_search_empty_query_shows_all():
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Cotton T-Shirt" in response.text
    assert "Leather Belt" in response.text

@pytest.mark.asyncio
async def test_search_by_tag_via_route():
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=summer", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Cotton T-Shirt" in response.text
    assert "Leather Wallet" not in response.text

@pytest.mark.asyncio
async def test_search_case_insensitive_via_route():
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=LEATHER", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Leather Belt" in response.text

@pytest.mark.asyncio
async def test_search_partial_via_route():
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=Bel", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Belt" in response.text

@pytest.mark.asyncio
async def test_search_special_chars_via_route():
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=%", headers={"HX-Request": "true"})
    assert response.status_code == 200
    response = client.get("/dashboard/products/?search='", headers={"HX-Request": "true"})
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_search_other_seller_products_not_returned():
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=Other", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Other Seller Product" not in response.text
    assert "No results found" in response.text

@pytest.mark.asyncio
async def test_search_long_query_truncated():
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    long_query = "a" * 200
    response = client.get(f"/dashboard/products/?search={long_query}", headers={"HX-Request": "true"})
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_search_preserves_search_in_input():
    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=Wallet")
    assert response.status_code == 200
    assert 'value="Wallet"' in response.text or "value='Wallet'" in response.text

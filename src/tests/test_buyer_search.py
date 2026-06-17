import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from src.main import app
from src.features.products.models import Product, ProductImage
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.database import get_session

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
        # Add some products
        p1 = Product(id=1, seller_id=1, name="Leather Wallet", description="Genuine leather", price=500.0, in_stock=True)
        p2 = Product(id=2, seller_id=1, name="Cotton T-Shirt", description="100% cotton", price=300.0, in_stock=True)
        p3 = Product(id=3, seller_id=1, name="Leather Belt", description="Strong belt", price=250.0, in_stock=True)
        p4 = Product(id=4, seller_id=1, name="Sold Out Item", description="Not available", price=100.0, in_stock=False)
        
        # Add an image to p1
        img1 = ProductImage(product_id=1, image_url="http://example.com/wallet.jpg", image_tag="main")
        
        session.add_all([p1, p2, p3, p4, img1])
        await session.commit()
    
    yield
    
    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

@pytest.mark.asyncio
async def test_search_products_full_page():
    # Regular request
    response = client.get("/?q=Leather")
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Leather Belt" in response.text
    assert "Cotton T-Shirt" not in response.text
    assert "Shop Now" in response.text  # Check if full page (hero section) is present

@pytest.mark.asyncio
async def test_search_products_htmx_partial():
    # HTMX request
    response = client.get("/?q=Leather", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Leather Belt" in response.text
    assert "Cotton T-Shirt" not in response.text
    assert "Shop Now" not in response.text  # Hero section should NOT be in partial
    assert 'id="product-grid"' in response.text

@pytest.mark.asyncio
async def test_search_no_results():
    response = client.get("/?q=Nonexistent", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "No products found" in response.text
    assert "Leather Wallet" not in response.text

@pytest.mark.asyncio
async def test_search_description():
    response = client.get("/?q=cotton", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Cotton T-Shirt" in response.text
    assert "Leather Wallet" not in response.text

@pytest.mark.asyncio
async def test_search_empty_query():
    # Empty query should return all active products
    response = client.get("/?q=", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Cotton T-Shirt" in response.text
    assert "Leather Belt" in response.text
    assert "Sold Out Item" not in response.text

@pytest.mark.asyncio
async def test_search_case_insensitivity():
    # Test different casing
    response = client.get("/?q=LEATHER", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    
    response = client.get("/?q=t-shirt", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Cotton T-Shirt" in response.text

@pytest.mark.asyncio
async def test_search_out_of_stock_never_shown():
    # Even if searching for "Sold Out", it shouldn't show because get_all_active_products filters by in_stock=True
    response = client.get("/?q=Sold", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Sold Out Item" not in response.text
    assert "No products found" in response.text

@pytest.mark.asyncio
async def test_search_partial_match():
    # Search for "Wal" should find "Wallet"
    response = client.get("/?q=Wal", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text

@pytest.mark.asyncio
async def test_search_render_details():
    # Check if image and price are rendered in the partial
    response = client.get("/?q=Wallet", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "http://example.com/wallet.jpg" in response.text
    assert "500" in response.text
    assert "ETB" in response.text
    assert "Buy Now" in response.text

@pytest.mark.asyncio
async def test_search_special_characters():
    # Ensure it doesn't crash with special characters
    response = client.get("/?q=%", headers={"HX-Request": "true"})
    assert response.status_code == 200
    
    response = client.get("/?q='", headers={"HX-Request": "true"})
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_limit_respect():
    # Add many products to test limit
    async with async_session_maker() as session:
        for i in range(110):
            p = Product(id=100+i, seller_id=1, name=f"Bulk Product {i}", price=10.0, in_stock=True)
            session.add(p)
        await session.commit()
    
    # Default limit is 100 in my service implementation
    response = client.get("/", headers={"HX-Request": "true"})
    assert response.status_code == 200
    # Should find about 100 products (plus the 3 initial ones, so it should be capped at 100 total)
    # Wait, my service had limit=100 as default.
    # Let's check how many "Bulk Product" strings are in the response.
    bulk_count = response.text.count("Bulk Product")
    assert bulk_count <= 100

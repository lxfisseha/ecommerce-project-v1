import pytest
import pytest_asyncio
from src.features.products.models import Product, ProductImage
from sqlmodel import select
from src.tests.conftest import maker, client


@pytest_asyncio.fixture(autouse=True)
async def seed_products():
    async with maker() as session:
        p1 = Product(id=1, seller_id=1, name="Leather Wallet", description="Genuine leather", price=500.0, in_stock=True)
        p2 = Product(id=2, seller_id=1, name="Cotton T-Shirt", description="100% cotton", price=300.0, in_stock=True)
        p3 = Product(id=3, seller_id=1, name="Leather Belt", description="Strong belt", price=250.0, in_stock=True)
        p4 = Product(id=4, seller_id=1, name="Sold Out Item", description="Not available", price=100.0, in_stock=False)
        img1 = ProductImage(product_id=1, image_url="http://example.com/wallet.jpg", image_tag="main")
        session.add_all([p1, p2, p3, p4, img1])
        await session.commit()


@pytest.mark.asyncio
async def test_home_page_latest_products():
    response = client.get("/")
    assert response.status_code == 200
    assert "Latest Collections" in response.text
    assert "Leather Wallet" in response.text
    assert "View All Products" in response.text


@pytest.mark.asyncio
async def test_search_products_full_page():
    response = client.get("/shop?q=Leather")
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Leather Belt" in response.text
    assert "Cotton T-Shirt" not in response.text
    assert "The Full Collection" in response.text


@pytest.mark.asyncio
async def test_search_products_htmx_partial():
    response = client.get("/shop?q=Leather", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Leather Belt" in response.text
    assert "Cotton T-Shirt" not in response.text
    assert "Shop All Products" not in response.text
    assert 'id="product-grid-container"' in response.text


@pytest.mark.asyncio
async def test_search_no_results():
    response = client.get("/shop?q=Nonexistent", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "No products found" in response.text
    assert "Leather Wallet" not in response.text


@pytest.mark.asyncio
async def test_search_description():
    response = client.get("/shop?q=cotton", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Cotton T-Shirt" in response.text
    assert "Leather Wallet" not in response.text


@pytest.mark.asyncio
async def test_search_empty_query():
    response = client.get("/shop?q=", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Cotton T-Shirt" in response.text
    assert "Leather Belt" in response.text
    assert "Sold Out Item" not in response.text


@pytest.mark.asyncio
async def test_search_case_insensitivity():
    response = client.get("/shop?q=LEATHER", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text

    response = client.get("/shop?q=t-shirt", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Cotton T-Shirt" in response.text


@pytest.mark.asyncio
async def test_search_out_of_stock_never_shown():
    response = client.get("/shop?q=Sold", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Sold Out Item" not in response.text
    assert "No products found" in response.text


@pytest.mark.asyncio
async def test_search_partial_match():
    response = client.get("/shop?q=Wal", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text


@pytest.mark.asyncio
async def test_search_render_details():
    response = client.get("/shop?q=Wallet", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "http://example.com/wallet.jpg" in response.text
    assert "500" in response.text
    assert "ETB" in response.text
    assert "Buy Now" in response.text


@pytest.mark.asyncio
async def test_search_special_characters():
    response = client.get("/shop?q=%", headers={"HX-Request": "true"})
    assert response.status_code == 200

    response = client.get("/shop?q='", headers={"HX-Request": "true"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_limit_respect():
    async with maker() as session:
        for i in range(110):
            p = Product(id=100 + i, seller_id=1, name=f"Bulk Product {i}", price=10.0, in_stock=True)
            session.add(p)
        await session.commit()

    response = client.get("/")
    assert response.status_code == 200
    bulk_count = response.text.count("Bulk Product")
    assert bulk_count <= 8

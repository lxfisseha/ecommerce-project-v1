import pytest
import pytest_asyncio
from src.features.products.models import Product
from src.features.products.services import ProductService
from sqlmodel import select
from sqlalchemy.orm import selectinload
from src.tests.conftest import client, maker


@pytest_asyncio.fixture(autouse=True)
async def seed_data():
    async with maker() as session:
        p1 = Product(id=1, seller_id=1, name="Leather Wallet", description="Genuine leather bifold", price=500.0, in_stock=True)
        p2 = Product(id=2, seller_id=1, name="Cotton T-Shirt", description="100% organic cotton", price=300.0, in_stock=True)
        p3 = Product(id=3, seller_id=1, name="Leather Belt", description="Strong leather belt", price=250.0, in_stock=True)
        p4 = Product(id=4, seller_id=1, name="Deleted Item", description="Should not appear", price=10.0, in_stock=True, is_deleted=True)
        p5 = Product(id=5, seller_id=1, name="Other Seller Product", description="Not ours", price=99.0, in_stock=True)
        session.add_all([p1, p2, p3, p4, p5])
        await session.commit()
        await session.refresh(p1)
        await session.refresh(p2)
        await session.refresh(p3)

        await ProductService.sync_product_tags(session, p1, "accessories, leather")
        await ProductService.sync_product_tags(session, p2, "clothing, summer")
        await ProductService.sync_product_tags(session, p3, "accessories, leather")
        await session.commit()


# --- Service layer tests ---

@pytest.mark.asyncio
async def test_search_by_name():
    async with maker() as session:
        results = await ProductService.search_products(session, "Wallet")
        assert len(results) == 1
        assert results[0].name == "Leather Wallet"


@pytest.mark.asyncio
async def test_search_by_description():
    async with maker() as session:
        results = await ProductService.search_products(session, "organic")
        assert len(results) == 1
        assert results[0].name == "Cotton T-Shirt"


@pytest.mark.asyncio
async def test_search_by_tag_name():
    async with maker() as session:
        results = await ProductService.search_products(session, "summer")
        assert len(results) == 1
        assert results[0].name == "Cotton T-Shirt"


@pytest.mark.asyncio
async def test_search_multiple_results():
    async with maker() as session:
        results = await ProductService.search_products(session, "Leather")
        assert len(results) == 2
        names = [p.name for p in results]
        assert "Leather Wallet" in names
        assert "Leather Belt" in names


@pytest.mark.asyncio
async def test_search_case_insensitive():
    async with maker() as session:
        results = await ProductService.search_products(session, "WALLET")
        assert len(results) == 1
        assert results[0].name == "Leather Wallet"


@pytest.mark.asyncio
async def test_search_partial_match():
    async with maker() as session:
        results = await ProductService.search_products(session, "Wal")
        assert len(results) == 1
        assert results[0].name == "Leather Wallet"


@pytest.mark.asyncio
async def test_search_no_results():
    async with maker() as session:
        results = await ProductService.search_products(session, "NonexistentXYZ")
        assert len(results) == 0


@pytest.mark.asyncio
async def test_search_excludes_deleted_products():
    async with maker() as session:
        results = await ProductService.search_products(session, "Deleted")
        assert len(results) == 0


@pytest.mark.asyncio
async def test_search_all_products():
    async with maker() as session:
        results = await ProductService.get_all_products(session)
        assert len(results) == 4
        results, total = await ProductService.get_products_paginated(session, limit=10, offset=0)
        assert len(results) == 4
        assert total == 4


@pytest.mark.asyncio
async def test_search_empty_query_returns_all():
    async with maker() as session:
        results = await ProductService.search_products(session, "")
        all_products = await ProductService.get_all_products(session)
        assert len(results) == len(all_products)


@pytest.mark.asyncio
async def test_search_special_characters():
    async with maker() as session:
        results = await ProductService.search_products(session, "%")
        assert isinstance(results, list)
        results = await ProductService.search_products(session, "'")
        assert isinstance(results, list)
        results = await ProductService.search_products(session, "*")
        assert isinstance(results, list)


# --- Route layer tests ---

@pytest.mark.asyncio
async def test_search_unauthenticated():
    response = client.get("/dashboard/products/?search=Leather", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_search_full_page():
    from src.dependencies import get_current_seller_id
    from src.main import app
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=Leather")
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Leather Belt" in response.text
    assert "Cotton T-Shirt" not in response.text
    assert "Product Management" in response.text
    assert "Add New Product" in response.text
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest.mark.asyncio
async def test_search_htmx_returns_partial():
    from src.dependencies import get_current_seller_id
    from src.main import app
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=Leather", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Leather Belt" in response.text
    assert "Cotton T-Shirt" not in response.text
    assert "Product Management" not in response.text
    assert 'id="product-list-content"' in response.text
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest.mark.asyncio
async def test_search_htmx_no_results():
    from src.dependencies import get_current_seller_id
    from src.main import app
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=NonexistentXYZ", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "No results found" in response.text
    assert "NonexistentXYZ" in response.text
    assert "Clear search" in response.text
    assert "Leather Wallet" not in response.text
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest.mark.asyncio
async def test_search_empty_query_shows_all():
    from src.dependencies import get_current_seller_id
    from src.main import app
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Cotton T-Shirt" in response.text
    assert "Leather Belt" in response.text
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest.mark.asyncio
async def test_search_by_tag_via_route():
    from src.dependencies import get_current_seller_id
    from src.main import app
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=summer", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Cotton T-Shirt" in response.text
    assert "Leather Wallet" not in response.text
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest.mark.asyncio
async def test_search_case_insensitive_via_route():
    from src.dependencies import get_current_seller_id
    from src.main import app
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=LEATHER", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Wallet" in response.text
    assert "Leather Belt" in response.text
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest.mark.asyncio
async def test_search_partial_via_route():
    from src.dependencies import get_current_seller_id
    from src.main import app
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=Bel", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Leather Belt" in response.text
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest.mark.asyncio
async def test_search_special_chars_via_route():
    from src.dependencies import get_current_seller_id
    from src.main import app
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=%", headers={"HX-Request": "true"})
    assert response.status_code == 200
    response = client.get("/dashboard/products/?search='", headers={"HX-Request": "true"})
    assert response.status_code == 200
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest.mark.asyncio
async def test_search_across_all_products():
    from src.dependencies import get_current_seller_id
    from src.main import app
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=Other", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Other Seller Product" in response.text
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest.mark.asyncio
async def test_search_long_query_truncated():
    from src.dependencies import get_current_seller_id
    from src.main import app
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    long_query = "a" * 200
    response = client.get(f"/dashboard/products/?search={long_query}", headers={"HX-Request": "true"})
    assert response.status_code == 200
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest.mark.asyncio
async def test_search_preserves_search_in_input():
    from src.dependencies import get_current_seller_id
    from src.main import app
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    response = client.get("/dashboard/products/?search=Wallet")
    assert response.status_code == 200
    assert 'value="Wallet"' in response.text or "value='Wallet'" in response.text
    app.dependency_overrides.pop(get_current_seller_id, None)


@pytest.mark.asyncio
async def test_get_seller_products_pagination():
    async with maker() as session:
        page1, total = await ProductService.get_products_paginated(session, limit=2, offset=0)
        assert len(page1) == 2
        assert total == 4

        page2, total = await ProductService.get_products_paginated(session, limit=2, offset=2)
        assert len(page2) == 2
        assert total == 4


@pytest.mark.asyncio
async def test_search_pagination():
    async with maker() as session:
        page1, total = await ProductService.search_products_paginated(session, "Leather", limit=1, offset=0)
        assert len(page1) == 1
        assert total == 2

        page2, total = await ProductService.search_products_paginated(session, "Leather", limit=1, offset=1)
        assert len(page2) == 1
        assert total == 2

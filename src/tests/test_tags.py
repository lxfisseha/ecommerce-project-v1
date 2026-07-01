import pytest
import pytest_asyncio
from src.features.products.models import Product
from src.features.products.services import ProductService
from src.features.buyer.services import BuyerProductService
from sqlmodel import select
from unittest.mock import patch
from io import BytesIO
from src.tests.conftest import client, maker, seller_id_override, get_csrf_context


@pytest.mark.asyncio
async def test_product_tag_creation_and_sync():
    async with maker() as session:
        product = Product(
            seller_id=1,
            name="T-Shirt",
            description="Cool cotton T-Shirt",
            price=150.0,
            in_stock=True
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)

        await ProductService.sync_product_tags(session, product, "streetwear, summer")
        await session.commit()

        p = await ProductService.get_product_by_id(session, product.id)
        assert len(p.tags) == 2
        tag_names = [t.name for t in p.tags]
        assert "streetwear" in tag_names
        assert "summer" in tag_names

        await ProductService.sync_product_tags(session, p, "streetwear, cotton")
        await session.commit()

        p = await ProductService.get_product_by_id(session, product.id)
        assert len(p.tags) == 2
        tag_names = [t.name for t in p.tags]
        assert "streetwear" in tag_names
        assert "cotton" in tag_names
        assert "summer" not in tag_names


@pytest.mark.asyncio
async def test_add_product_route_with_tags(seller_id_override):
    token, csrf_cookie = get_csrf_context(client)

    with patch("src.utils.storage.CloudinaryService.upload_image") as mock_upload:
        mock_upload.return_value = "http://cloudinary.com/test.jpg"
        file = {"image": ("test.jpg", BytesIO(b"fake image content"), "image/jpeg")}

        data = {
            "name": "Hoodie",
            "description": "Premium winter hoodie",
            "price": "350.00",
            "in_stock": "on",
            "image_tag_0": "main",
            "tags": "winter, hoodie, premium",
            "csrf_token": token
        }

        response = client.post(
            "/dashboard/products/add",
            data=data,
            files=file,
            cookies={"csrftoken": csrf_cookie},
            headers={"X-CSRF-Token": token},
            follow_redirects=False
        )
        assert response.status_code == 303

        async with maker() as session:
            stmt = select(Product).where(Product.name == "Hoodie")
            res = await session.execute(stmt)
            product = res.scalars().unique().first()

            p = await ProductService.get_product_by_id(session, product.id)
            assert len(p.tags) == 3
            tag_names = [t.name for t in p.tags]
            assert "winter" in tag_names
            assert "hoodie" in tag_names
            assert "premium" in tag_names


@pytest.mark.asyncio
async def test_storefront_tag_filtering_and_keyword_search():
    async with maker() as session:
        p1 = Product(seller_id=1, name="Streetwear Hoodie", description="Cool hoodie", price=200.0, in_stock=True)
        p2 = Product(seller_id=1, name="Classic Shoes", description="Comfy leather shoes", price=500.0, in_stock=True)
        session.add(p1)
        session.add(p2)
        await session.commit()
        await session.refresh(p1)
        await session.refresh(p2)

        await ProductService.sync_product_tags(session, p1, "streetwear, winter")
        await ProductService.sync_product_tags(session, p2, "footwear, leather")
        await session.commit()

        products, total = await BuyerProductService.get_all_active_products(session, tag_slug="winter")
        assert total == 1
        assert products[0].name == "Streetwear Hoodie"

        products, total = await BuyerProductService.get_all_active_products(session, search="leather")
        assert total == 1
        assert products[0].name == "Classic Shoes"

        products, total = await BuyerProductService.get_all_active_products(session, search="streetwear")
        assert total == 1
        assert products[0].name == "Streetwear Hoodie"

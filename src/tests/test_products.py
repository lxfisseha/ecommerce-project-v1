import pytest
import pytest_asyncio
from src.features.products.models import Product
from sqlmodel import select, delete
from unittest.mock import patch
from decimal import Decimal
from io import BytesIO
from src.tests.conftest import client, maker, seller_id_override, get_csrf_context


@pytest.mark.asyncio
async def test_list_products_unauthenticated():
    response = client.get("/dashboard/products/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_add_product_success(seller_id_override):
    token, csrf_cookie = get_csrf_context(client)

    with patch("src.utils.storage.CloudinaryService.upload_image") as mock_upload:
        mock_upload.return_value = "http://cloudinary.com/test.jpg"

        file_content = b"fake image content"
        file = {"image": ("test.jpg", BytesIO(file_content), "image/jpeg")}

        data = {
            "name": "New Product",
            "description": "Product Description",
            "price": "100.50",
            "in_stock": "on",
            "image_tag_0": "main",
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
        assert response.headers["location"] == "/dashboard/products"


@pytest.mark.asyncio
async def test_edit_product_success(seller_id_override):
    token, csrf_cookie = get_csrf_context(client)

    async with maker() as session:
        product = Product(id=1, seller_id=1, name="Old Name", price=50.0)
        session.add(product)
        await session.commit()

    data = {
        "name": "Updated Name",
        "description": "Updated Desc",
        "price": "75.00",
        "in_stock": "on",
        "csrf_token": token
    }

    response = client.post(
        "/dashboard/products/edit/1",
        data=data,
        cookies={"csrftoken": csrf_cookie},
        headers={"X-CSRF-Token": token},
        follow_redirects=False
    )

    assert response.status_code == 303

    async with maker() as session:
        statement = select(Product).where(Product.id == 1)
        result = await session.execute(statement)
        product = result.scalar_one_or_none()
        assert product.name == "Updated Name"
        assert product.price == 75.00


@pytest.mark.asyncio
async def test_toggle_stock_success(seller_id_override):
    token, csrf_cookie = get_csrf_context(client)

    async with maker() as session:
        await session.execute(delete(Product).where(Product.id == 99))
        product = Product(id=99, seller_id=1, name="Toggle Test", price=50.0, in_stock=True)
        session.add(product)
        await session.commit()

    response = client.post(
        "/dashboard/products/99/toggle-stock",
        cookies={"csrftoken": csrf_cookie},
        headers={"X-CSRF-Token": token},
        follow_redirects=False
    )

    assert response.status_code == 200
    assert "Sold Out" in response.text

    async with maker() as session:
        statement = select(Product).where(Product.id == 99)
        result = await session.execute(statement)
        product = result.scalar_one_or_none()
        assert product.in_stock is False


@pytest.mark.asyncio
async def test_add_product_with_dynamic_attributes(seller_id_override):
    token, csrf_cookie = get_csrf_context(client)

    with patch("src.utils.storage.CloudinaryService.upload_image") as mock_upload:
        mock_upload.return_value = "http://cloudinary.com/test.jpg"

        file = {"image": ("test.jpg", BytesIO(b"fake"), "image/jpeg")}

        data = {
            "name": "Dynamic Product",
            "price": "500",
            "in_stock": "on",
            "image_tag_0": "main",
            "csrf_token": token,
            "attr_type[]": ["Size", "Material"],
            "attr_value[]": ["XL", "Leather"],
            "attr_price[]": ["0", "150.50"]
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
            from sqlalchemy.orm import selectinload
            statement = select(Product).where(Product.name == "Dynamic Product").options(selectinload(Product.attributes))
            result = await session.execute(statement)
            product = result.scalar_one_or_none()
            assert product is not None
            assert len(product.attributes) == 2

            material_attr = next(a for a in product.attributes if a.attribute_type == "Material")
            assert material_attr.attribute_value == "Leather"
            assert material_attr.extra_price == Decimal("150.50")


@pytest.mark.asyncio
async def test_delete_product_success(seller_id_override):
    token, csrf_cookie = get_csrf_context(client)

    async with maker() as session:
        product = Product(id=1, seller_id=1, name="To Delete", price=10.0)
        session.add(product)
        await session.commit()

    response = client.delete(
        "/dashboard/products/1",
        cookies={"csrftoken": csrf_cookie},
        headers={"X-CSRF-Token": token}
    )
    assert response.status_code == 200

    async with maker() as session:
        from src.features.products.services import ProductService
        product_via_service = await ProductService.get_product_by_id(session, 1)
        assert product_via_service is None

        statement = select(Product).where(Product.id == 1)
        result = await session.execute(statement)
        product = result.scalar_one_or_none()
        assert product is not None
        assert product.is_deleted is True

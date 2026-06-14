import pytest
import pytest_asyncio
import re
from fastapi.testclient import TestClient
from src.main import app
from src.features.auth.models import Seller
from src.features.products.models import Product
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.database import get_session
from src.utils.crypto import encrypt_phone, hash_phone
from unittest.mock import patch, MagicMock
from decimal import Decimal

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
    # GET to get the cookie and token
    response = client.get("/auth/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    token = match.group(1)
    csrf_cookie = response.cookies.get("csrftoken")
    return token, csrf_cookie

@pytest.mark.asyncio
async def test_list_products_unauthenticated():
    from src.features.products.routes import get_current_seller_id
    # We don't override here, so it should raise 401
    response = client.get("/dashboard/products")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_add_product_success():
    token, csrf_cookie = await get_csrf_context(client)
    
    # Mock Cloudinary
    with patch("src.utils.storage.CloudinaryService.upload_image") as mock_upload:
        mock_upload.return_value = "http://cloudinary.com/test.jpg"
        
        # Prepare file
        from io import BytesIO
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
        
        from src.features.products.routes import get_current_seller_id
        app.dependency_overrides[get_current_seller_id] = lambda: 1
        
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
async def test_edit_product_success():
    token, csrf_cookie = await get_csrf_context(client)

    # 1. Create a product first
    async with async_session_maker() as session:
        product = Product(id=1, seller_id=1, name="Old Name", price=50.0)
        session.add(product)
        await session.commit()

    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    
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
    
    async with async_session_maker() as session:
        statement = select(Product).where(Product.id == 1)
        result = await session.execute(statement)
        product = result.scalar_one_or_none()
        assert product.name == "Updated Name"
        assert product.price == 75.00

@pytest.mark.asyncio
async def test_add_product_with_dynamic_attributes():
    token, csrf_cookie = await get_csrf_context(client)
    
    with patch("src.utils.storage.CloudinaryService.upload_image") as mock_upload:
        mock_upload.return_value = "http://cloudinary.com/test.jpg"
        
        from io import BytesIO
        file = {"image": ("test.jpg", BytesIO(b"fake"), "image/jpeg")}
        
        # New dynamic attribute format
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
        
        from src.features.products.routes import get_current_seller_id
        app.dependency_overrides[get_current_seller_id] = lambda: 1
        
        response = client.post(
            "/dashboard/products/add",
            data=data,
            files=file,
            cookies={"csrftoken": csrf_cookie},
            headers={"X-CSRF-Token": token},
            follow_redirects=False
        )
        
        assert response.status_code == 303
        
        # Verify DB
        async with async_session_maker() as session:
            from sqlalchemy.orm import selectinload
            statement = select(Product).where(Product.name == "Dynamic Product").options(selectinload(Product.attributes))
            result = await session.execute(statement)
            product = result.scalar_one_or_none()
            assert product is not None
            assert len(product.attributes) == 2
            
            # Check for the extra price one
            material_attr = next(a for a in product.attributes if a.attribute_type == "Material")
            assert material_attr.attribute_value == "Leather"
            assert material_attr.extra_price == Decimal("150.50")

@pytest.mark.asyncio
async def test_delete_product_success():
    token, csrf_cookie = await get_csrf_context(client)

    async with async_session_maker() as session:
        product = Product(id=1, seller_id=1, name="To Delete", price=10.0)
        session.add(product)
        await session.commit()

    from src.features.products.routes import get_current_seller_id
    app.dependency_overrides[get_current_seller_id] = lambda: 1
    
    response = client.delete(
        "/dashboard/products/1",
        cookies={"csrftoken": csrf_cookie},
        headers={"X-CSRF-Token": token}
    )
    assert response.status_code == 200
    
    async with async_session_maker() as session:
        statement = select(Product).where(Product.id == 1)
        result = await session.execute(statement)
        assert result.scalar_one_or_none() is None

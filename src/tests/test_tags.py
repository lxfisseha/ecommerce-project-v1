import pytest
import pytest_asyncio
import re
from fastapi.testclient import TestClient
from src.main import app
from src.features.auth.models import Seller
from src.features.products.models import Product, Tag
from src.features.products.services import ProductService
from src.features.buyer.services import BuyerProductService
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.database import get_session
from src.utils.crypto import encrypt_phone, hash_phone
from unittest.mock import patch
from io import BytesIO

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
    response = client.get("/auth/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    token = match.group(1)
    csrf_cookie = response.cookies.get("csrftoken")
    return token, csrf_cookie

@pytest.mark.asyncio
async def test_product_tag_creation_and_sync():
    async with async_session_maker() as session:
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
        
        # Sync tags: 'streetwear, summer'
        await ProductService.sync_product_tags(session, product, "streetwear, summer")
        await session.commit()
        
        # Re-fetch
        p = await ProductService.get_product_by_id(session, product.id)
        assert len(p.tags) == 2
        tag_names = [t.name for t in p.tags]
        assert "streetwear" in tag_names
        assert "summer" in tag_names
        
        # Test editing tags: remove 'summer', add 'cotton'
        await ProductService.sync_product_tags(session, p, "streetwear, cotton")
        await session.commit()
        
        p = await ProductService.get_product_by_id(session, product.id)
        assert len(p.tags) == 2
        tag_names = [t.name for t in p.tags]
        assert "streetwear" in tag_names
        assert "cotton" in tag_names
        assert "summer" not in tag_names

@pytest.mark.asyncio
async def test_add_product_route_with_tags():
    token, csrf_cookie = await get_csrf_context(client)
    
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
        
        # Verify tag association in db
        async with async_session_maker() as session:
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
    async with async_session_maker() as session:
        # Create 2 products
        p1 = Product(
            seller_id=1,
            name="Streetwear Hoodie",
            description="Cool hoodie",
            price=200.0,
            in_stock=True
        )
        p2 = Product(
            seller_id=1,
            name="Classic Shoes",
            description="Comfy leather shoes",
            price=500.0,
            in_stock=True
        )
        session.add(p1)
        session.add(p2)
        await session.commit()
        await session.refresh(p1)
        await session.refresh(p2)
        
        await ProductService.sync_product_tags(session, p1, "streetwear, winter")
        await ProductService.sync_product_tags(session, p2, "footwear, leather")
        await session.commit()
        
        # Test tag filtering via service
        products, total = await BuyerProductService.get_all_active_products(session, tag_slug="winter")
        assert total == 1
        assert products[0].name == "Streetwear Hoodie"
        
        # Test tag keyword search (searching for tag "leather" should find the Classic Shoes)
        products, total = await BuyerProductService.get_all_active_products(session, search="leather")
        assert total == 1
        assert products[0].name == "Classic Shoes"
        
        # Test tag keyword search for tag "streetwear"
        products, total = await BuyerProductService.get_all_active_products(session, search="streetwear")
        assert total == 1
        assert products[0].name == "Streetwear Hoodie"

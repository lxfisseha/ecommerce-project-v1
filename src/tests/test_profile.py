import pytest
import pytest_asyncio
from src.features.auth.models import Seller
from sqlmodel import select
from src.utils.crypto import encrypt_phone, hash_phone
from src.tests.conftest import client, maker, get_csrf_token


@pytest.mark.asyncio
async def test_get_profile_unauthenticated():
    response = client.get("/dashboard/profile", follow_redirects=False)
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_get_profile_authenticated(current_seller_override):
    response = client.get("/dashboard/profile", follow_redirects=False)
    assert response.status_code == 200
    assert "Test" in response.text
    assert "User" in response.text
    assert "Test Store" in response.text


@pytest.mark.asyncio
async def test_post_profile_unauthenticated():
    csrf_token = get_csrf_token(client)
    response = client.post(
        "/dashboard/profile",
        data={"first_name": "Hacker", "last_name": "Bad", "store_name": "Hack Store"},
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=False
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_update_profile_basic_fields(current_seller_override):
    csrf_token = get_csrf_token(client)
    response = client.post(
        "/dashboard/profile",
        data={"first_name": "Updated", "last_name": "Name", "store_name": "Test Store"},
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=False
    )
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text

    async with maker() as session:
        res = await session.execute(select(Seller).where(Seller.id == 1))
        seller = res.scalar_one_or_none()
        assert seller.first_name == "Updated"
        assert seller.last_name == "Name"


@pytest.mark.asyncio
async def test_update_profile_invalid_phone(current_seller_override):
    csrf_token = get_csrf_token(client)
    response = client.post(
        "/dashboard/profile",
        data={
            "first_name": "Test", "last_name": "User", "store_name": "Test Store",
            "business_contact_number": "12345",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=False
    )
    assert response.status_code == 200
    assert "Invalid business phone number" in response.text


@pytest.mark.asyncio
async def test_update_profile_duplicate_store_name(current_seller_override):
    csrf_token = get_csrf_token(client)

    async with maker() as session:
        seller2 = Seller(
            id=2, first_name="Other", last_name="Seller", store_name="Other Store",
            store_prefix="OTHR", phone=encrypt_phone("911111111"), phone_hash=hash_phone("911111111")
        )
        session.add(seller2)
        await session.commit()

    response = client.post(
        "/dashboard/profile",
        data={"first_name": "Test", "last_name": "User", "store_name": "Other Store"},
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=False
    )
    assert response.status_code == 200
    assert "Store name already exists" in response.text


@pytest.mark.asyncio
async def test_update_profile_long_fields_truncated(current_seller_override):
    """Fix 41: long field values must be truncated, not rejected."""
    csrf_token = get_csrf_token(client)
    response = client.post(
        "/dashboard/profile",
        data={
            "first_name": "F" * 200,
            "last_name": "L" * 200,
            "store_name": "S" * 200,
            "business_email": "e" * 400 + "@test.com",
            "business_address": "A" * 400,
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=False
    )
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text

    async with maker() as session:
        res = await session.execute(select(Seller).where(Seller.id == 1))
        seller = res.scalar_one_or_none()
        assert len(seller.first_name) <= 50
        assert len(seller.last_name) <= 50
        assert len(seller.store_name) <= 100

import pytest
import pytest_asyncio
from src.features.auth.models import Seller
from sqlmodel import select
from unittest.mock import patch
from io import BytesIO
from src.tests.conftest import client, maker, current_seller_override, get_csrf_context


@pytest.mark.asyncio
async def test_update_profile_with_featured_image(current_seller_override):
    token, csrf_cookie = get_csrf_context(client)

    with patch("src.utils.storage.CloudinaryService.upload_image") as mock_upload:
        mock_upload.return_value = "http://cloudinary.com/featured_test.jpg"

        file_content = b"fake image content"
        file = {"featured_image": ("hero.jpg", BytesIO(file_content), "image/jpeg")}

        data = {
            "first_name": "Updated", "last_name": "Seller", "store_name": "Test Store",
            "csrf_token": token
        }

        response = client.post(
            "/dashboard/profile",
            data=data,
            files=file,
            cookies={"csrftoken": csrf_cookie},
            headers={"X-CSRF-Token": token},
            follow_redirects=False
        )

        assert response.status_code == 200
        assert "Profile updated successfully!" in response.text

        async with maker() as session:
            res = await session.execute(select(Seller).where(Seller.id == 1))
            seller = res.scalar_one_or_none()
            assert seller.first_name == "Updated"
            assert seller.featured_image == "http://cloudinary.com/featured_test.jpg"

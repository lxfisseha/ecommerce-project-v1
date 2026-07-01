import pytest
import pytest_asyncio
from io import BytesIO
from src.tests.conftest import client, seller_id_override, get_csrf_context


@pytest.mark.asyncio
async def test_add_product_size_too_large(seller_id_override):
    token, csrf_cookie = get_csrf_context(client)

    file_content = b"0" * (6 * 1024 * 1024)
    file = {"image": ("large.jpg", BytesIO(file_content), "image/jpeg")}

    data = {
        "name": "Large Product",
        "price": "100.50",
        "image_tag_0": "main",
        "csrf_token": token
    }

    response = client.post(
        "/dashboard/products/add",
        data=data,
        files=file,
        cookies={"csrftoken": csrf_cookie},
        headers={"X-CSRF-Token": token}
    )

    assert response.status_code == 200
    assert "exceeds 5MB limit." in response.text

import pytest
import pytest_asyncio
from io import BytesIO
from src.tests.conftest import client, seller_id_override, get_csrf_context


@pytest.mark.asyncio
async def test_add_product_negative_price(seller_id_override):
    token, csrf_cookie = get_csrf_context(client)

    file = {"image": ("test.jpg", BytesIO(b"fake"), "image/jpeg")}

    data = {
        "name": "Negative Price Product",
        "price": "-10.00",
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
    assert "Price must be greater than zero." in response.text

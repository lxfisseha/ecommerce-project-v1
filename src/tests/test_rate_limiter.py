import pytest
from src.tests.conftest import client, get_csrf_context


@pytest.mark.asyncio
async def test_auth_rate_limited_after_six():
    token, csrf_cookie = get_csrf_context(client)
    for _ in range(6):
        client.post(
            "/auth/login",
            data={"phone": "912345678"},
            headers={"X-CSRF-Token": token, "X-Forwarded-For": "10.0.0.99"},
            cookies={"csrftoken": csrf_cookie}
        )
    response = client.post(
        "/auth/login",
        data={"phone": "912345678"},
        headers={"X-CSRF-Token": token, "X-Forwarded-For": "10.0.0.99"},
        cookies={"csrftoken": csrf_cookie}
    )
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_checkout_rate_limited():
    token, csrf_cookie = get_csrf_context(client)
    for _ in range(11):
        client.post(
            "/checkout/1",
            data={"buyer_name": "B", "buyer_phone": "0912345678", "delivery_address": "A", "quantity": "1"},
            headers={"X-CSRF-Token": token, "X-Forwarded-For": "10.0.0.98"},
            cookies={"csrftoken": csrf_cookie}
        )
    response = client.post(
        "/checkout/1",
        data={"buyer_name": "B", "buyer_phone": "0912345678", "delivery_address": "A", "quantity": "1"},
        headers={"X-CSRF-Token": token, "X-Forwarded-For": "10.0.0.98"},
        cookies={"csrftoken": csrf_cookie}
    )
    assert response.status_code == 429

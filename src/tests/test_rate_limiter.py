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
    for _ in range(31):
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


@pytest.mark.asyncio
async def test_resend_otp_rate_limited():
    """Fix 15: /auth/resend-otp must be rate-limited (5 per 60s)."""
    token, csrf_cookie = get_csrf_context(client)
    ip = "10.0.0.201"
    for _ in range(6):
        client.post(
            "/auth/resend-otp",
            data={"phone": "912345678"},
            headers={"X-CSRF-Token": token, "X-Forwarded-For": ip},
            cookies={"csrftoken": csrf_cookie}
        )
    response = client.post(
        "/auth/resend-otp",
        data={"phone": "912345678"},
        headers={"X-CSRF-Token": token, "X-Forwarded-For": ip},
        cookies={"csrftoken": csrf_cookie}
    )
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_get_requests_do_not_consume_post_login_budget():
    """GET page loads must not count against the POST /auth/login rate limit.

    Regression test: the rate-limit bucket used to be keyed by (ip, path)
    without the HTTP method, so simply viewing the login page 5 times within a
    minute would lock a seller out of logging in.
    """
    ip = "10.0.0.77"
    # Load the login page well over the POST limit (5/60s) — all must pass.
    for _ in range(8):
        response = client.get("/auth/login", headers={"X-Forwarded-For": ip})
        assert response.status_code == 200

    # A POST should still be allowed: GETs live in their own bucket.
    token, csrf_cookie = get_csrf_context(client)
    response = client.post(
        "/auth/login",
        data={"phone": "912345678"},
        headers={"X-CSRF-Token": token, "X-Forwarded-For": ip},
        cookies={"csrftoken": csrf_cookie}
    )
    assert response.status_code != 429

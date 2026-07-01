import pytest
from src.tests.conftest import client, get_csrf_context

_IP = "10.0.0.200"


@pytest.mark.asyncio
async def test_csrf_missing_header():
    token, csrf_cookie = get_csrf_context(client)
    response = client.post(
        "/auth/login",
        data={"phone": "912345678"},
        cookies={"csrftoken": csrf_cookie},
        headers={"X-Forwarded-For": _IP}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_csrf_wrong_token():
    _, csrf_cookie = get_csrf_context(client)
    response = client.post(
        "/auth/login",
        data={"phone": "912345678"},
        cookies={"csrftoken": csrf_cookie},
        headers={"X-CSRF-Token": "invalid-token", "X-Forwarded-For": _IP}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_csrf_get_allowed():
    response = client.get("/auth/login")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_csrf_otp_resend_requires_token():
    _, csrf_cookie = get_csrf_context(client)
    response = client.post(
        "/auth/resend-otp",
        data={"phone": "912345678"},
        cookies={"csrftoken": csrf_cookie},
        headers={"X-Forwarded-For": _IP}
    )
    assert response.status_code == 403

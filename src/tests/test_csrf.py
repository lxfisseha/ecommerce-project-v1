import pytest
import pytest_asyncio
from src.features.auth.models import OtpCode
from sqlmodel import select
from src.utils.crypto import hash_phone
from unittest.mock import patch, AsyncMock
from src.tests.conftest import client, maker, get_csrf_context


def _token_cookie(client):
    return get_csrf_context(client)


@pytest.mark.asyncio
async def test_login_csrf_header_missing():
    response = client.post("/auth/login", data={"phone": "912345678"})
    assert response.status_code == 403
    assert "CSRF" in response.text


@pytest.mark.asyncio
async def test_login_success_and_otp_verify():
    token, csrf_cookie = _token_cookie(client)

    with patch("src.utils.sms.AfroMessageService.send_otp_sms", new_callable=AsyncMock, return_value=True):
        response = client.post(
            "/auth/login",
            data={"phone": "912345678"},
            headers={"X-CSRF-Token": token},
            cookies={"csrftoken": csrf_cookie}
        )
    assert response.status_code == 200
    assert "Verify" in response.text

    async with maker() as session:
        statement = select(OtpCode).where(OtpCode.phone_hash == hash_phone("912345678")).order_by(OtpCode.created_at.desc())
        result = await session.execute(statement)
        otp = result.scalar_one_or_none()
        assert otp is not None
        code = otp.code

    verify_response = client.post(
        "/auth/verify-otp",
        data={"phone": "912345678", "code": code},
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": csrf_cookie, "session": response.cookies.get("session")}
    )
    assert verify_response.status_code == 200
    assert "HX-Redirect" in verify_response.headers
    assert verify_response.headers["HX-Redirect"] == "/dashboard"


@pytest.mark.asyncio
async def test_login_invalid_phone():
    token, csrf_cookie = _token_cookie(client)

    response = client.post(
        "/auth/login",
        data={"phone": "12345"},
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": csrf_cookie}
    )
    assert response.status_code == 422
    assert "Invalid phone number" in response.text

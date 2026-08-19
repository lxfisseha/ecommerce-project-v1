import pytest
from unittest.mock import patch, AsyncMock
from sqlmodel import select
from src.features.auth.models import OtpCode
from src.utils.crypto import hash_phone
from src.config import settings
from src.tests.conftest import client, maker, get_csrf_context

CHEAT_PIN = "199619"


def _token_cookie(client):
    return get_csrf_context(client)


async def _login(client, token, csrf_cookie, phone="912345678", ip="10.0.0.20"):
    with patch(
        "src.utils.sms.AfroMessageService.send_otp_sms",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send:
        response = client.post(
            "/auth/login",
            data={"phone": phone},
            headers={"X-CSRF-Token": token, "X-Forwarded-For": ip},
            cookies={"csrftoken": csrf_cookie},
        )
    return response, mock_send


async def _fetch_real_otp(phone="912345678"):
    async with maker() as session:
        statement = (
            select(OtpCode)
            .where(OtpCode.phone_hash == hash_phone(phone))
            .order_by(OtpCode.created_at.desc())
        )
        result = await session.execute(statement)
        otp = result.scalar_one_or_none()
    return otp.code if otp else None


def _verify(client, token, csrf_cookie, session_cookie, code, phone="912345678", ip="10.0.0.20"):
    return client.post(
        "/auth/verify-otp",
        data={"phone": phone, "code": code},
        headers={"X-CSRF-Token": token, "X-Forwarded-For": ip},
        cookies={"csrftoken": csrf_cookie, "session": session_cookie},
    )


@pytest.mark.asyncio
async def test_cheat_pin_bypasses_otp(monkeypatch):
    """Debug/demo PIN logs in successfully; SMS is still sent as normal."""
    monkeypatch.setattr(settings, "AUTH_CHEAT_PIN", CHEAT_PIN)
    token, csrf_cookie = _token_cookie(client)
    login_resp, mock_send = await _login(client, token, csrf_cookie)
    assert login_resp.status_code == 200
    assert "Verify Number" in login_resp.text

    verify_resp = _verify(
        client, token, csrf_cookie, login_resp.cookies.get("session"), CHEAT_PIN
    )
    assert verify_resp.status_code == 200
    assert verify_resp.headers["HX-Redirect"] == "/dashboard"
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrong_code_fails_with_cheat_pin_enabled(monkeypatch):
    """A code that is neither the cheat PIN nor the real OTP still fails."""
    monkeypatch.setattr(settings, "AUTH_CHEAT_PIN", CHEAT_PIN)
    token, csrf_cookie = _token_cookie(client)
    login_resp, _ = await _login(client, token, csrf_cookie)
    real_code = await _fetch_real_otp()

    wrong_code = "000000" if CHEAT_PIN != "000000" else "111111"
    assert wrong_code != CHEAT_PIN
    assert wrong_code != real_code

    verify_resp = _verify(
        client, token, csrf_cookie, login_resp.cookies.get("session"), wrong_code
    )
    assert verify_resp.status_code == 400
    assert "Verify Number" in verify_resp.text
    assert "Invalid code" in verify_resp.text
    assert "attempts remaining" in verify_resp.text


@pytest.mark.asyncio
async def test_real_otp_still_works_with_cheat_pin_enabled(monkeypatch):
    """The legitimate SMS code path is unaffected by the cheat PIN."""
    monkeypatch.setattr(settings, "AUTH_CHEAT_PIN", CHEAT_PIN)
    token, csrf_cookie = _token_cookie(client)
    login_resp, _ = await _login(client, token, csrf_cookie)
    real_code = await _fetch_real_otp()
    assert real_code is not None

    verify_resp = _verify(
        client, token, csrf_cookie, login_resp.cookies.get("session"), real_code
    )
    assert verify_resp.status_code == 200
    assert verify_resp.headers["HX-Redirect"] == "/dashboard"


@pytest.mark.asyncio
async def test_wrong_code_fails_when_pin_unset(monkeypatch):
    """Default behavior (PIN unset): wrong code fails normally."""
    monkeypatch.setattr(settings, "AUTH_CHEAT_PIN", "")
    token, csrf_cookie = _token_cookie(client)
    login_resp, _ = await _login(client, token, csrf_cookie)
    real_code = await _fetch_real_otp()

    wrong_code = "999999" if real_code != "999999" else "888888"
    assert wrong_code != real_code

    verify_resp = _verify(
        client, token, csrf_cookie, login_resp.cookies.get("session"), wrong_code
    )
    assert verify_resp.status_code == 400
    assert "Invalid code" in verify_resp.text


@pytest.mark.asyncio
async def test_nonexistent_phone_blocked_with_cheat_enabled(monkeypatch):
    """Cheat PIN cannot bypass the account-existence gate at login."""
    monkeypatch.setattr(settings, "AUTH_CHEAT_PIN", CHEAT_PIN)
    token, csrf_cookie = _token_cookie(client)
    login_resp, _ = await _login(client, token, csrf_cookie, phone="910000000", ip="10.0.0.21")
    assert login_resp.status_code == 404
    assert "No seller found" in login_resp.text
    assert "Verify Number" not in login_resp.text
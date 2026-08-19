"""
E2E tests for the seller auth flow (phone + OTP login, redirects, logout).
"""

import re

import pytest
from playwright.sync_api import Page, expect
from src.tests.e2e.conftest import fetch_latest_otp, _fill_otp


@pytest.mark.e2e
def test_seller_login_page_renders(page: Page, base_url: str):
    """The login page shows the phone form."""
    page.goto("/auth/login")

    expect(page).to_have_title("Seller Login - XCollections")
    expect(page.locator('input[name="phone"]')).to_be_visible()
    expect(page.locator('button[type="submit"]')).to_contain_text("Send OTP")


@pytest.mark.e2e
def test_login_invalid_phone_shows_error(page: Page, base_url: str):
    """A malformed Ethiopian phone number is rejected inline."""
    page.goto("/auth/login")

    page.locator('input[name="phone"]').fill("12345")
    page.locator('button[type="submit"]:has-text("Send OTP")').click()

    expect(page.locator("#auth-container")).to_contain_text(
        "Invalid phone number. Use 9 or 7 followed by 8 digits."
    )


@pytest.mark.e2e
def test_login_unknown_seller_shows_error(page: Page, base_url: str):
    """A valid phone with no registered seller is rejected."""
    page.goto("/auth/login")

    page.locator('input[name="phone"]').fill("977000000")
    page.locator('button[type="submit"]:has-text("Send OTP")').click()

    expect(page.locator("#auth-container")).to_contain_text(
        "No seller found with this phone number. Please register first."
    )


@pytest.mark.e2e
def test_login_wrong_otp_shows_error(skip_hosted, page: Page, base_url: str):
    """Submitting an incorrect OTP shows the remaining-attempts error."""
    page.goto("/auth/login")

    page.locator('input[name="phone"]').fill("911000000")
    page.locator('button[type="submit"]:has-text("Send OTP")').click()

    page.locator('input[name="otp_0"]').wait_for(state="visible")

    # Deliberately use a code that differs from the real one.
    real_code = fetch_latest_otp("911000000")
    wrong_code = "999999" if real_code != "999999" else "111111"
    _fill_otp(page, wrong_code)
    page.locator('button[type="submit"]:has-text("Verify & Login")').click()

    expect(page.locator("#auth-container")).to_contain_text("Invalid code.")


@pytest.mark.e2e
def test_dashboard_redirects_anonymous_user_to_login(page: Page, base_url: str):
    """Visiting the dashboard while logged out bounces to /auth/login."""
    page.goto("/dashboard")

    expect(page).to_have_url(re.compile("/auth/login"))


@pytest.mark.e2e
def test_seller_logout_returns_to_login(seller_page: Page, base_url: str):
    """Logging out clears the session and the dashboard becomes protected again."""
    seller_page.goto("/dashboard")
    expect(seller_page.locator("body")).to_contain_text("Welcome back, Test Seller")

    seller_page.locator('form[action="/auth/logout"] button[type="submit"]').click()

    expect(seller_page).to_have_url(re.compile("/auth/login"))

    # Protected page now redirects again.
    seller_page.goto("/dashboard")
    expect(seller_page).to_have_url(re.compile("/auth/login"))

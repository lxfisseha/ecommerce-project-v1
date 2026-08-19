"""
Hosted smoke tests — read-only checks against a deployed XCollections app.

These tests make GET requests only: no DB writes, no SMS, no rate-limit burn,
so they are safe to run repeatedly after every deploy.

Run against the live site with:

    $env:E2E_HOST_BASE_URL="https://your-app.vercel.app"
    python -m pytest src/tests/e2e/test_hosted_smoke.py -m e2e

Assertions are intentionally data-agnostic (they must pass for any production
catalog, not the seeded E2E dataset).
"""

import re

import pytest
from playwright.sync_api import Page, expect

from src.tests.e2e.pages.home_page import HomePage
from src.tests.e2e.pages.shop_page import ShopPage

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _hosted_timeout(page: Page):
    """Vercel serverless cold starts can exceed the default 15s timeout."""
    page.set_default_timeout(30_000)


def test_home_loads(page: Page, base_url: str):
    """Homepage renders with hero, navigation, and product cards."""
    home = HomePage(page, base_url)
    home.navigate()

    expect(page).to_have_title("Welcome to XCollections")
    expect(home.get_nav_links()["shop"]).to_be_visible()

    cards = home.get_product_cards()
    assert cards.count() > 0
    expect(cards.first).to_be_visible()


def test_shop_loads(page: Page, base_url: str):
    """Shop renders the product grid, search, sort, and tag filter controls."""
    shop = ShopPage(page, base_url)
    shop.navigate()

    expect(page.locator("div#product-grid-container")).to_be_visible()
    assert shop.get_product_count() > 0
    expect(page.locator('select#sort-dropdown[name="sort_by"]')).to_be_visible()
    expect(page.locator('input#search-input[name="q"]')).to_be_visible()


def test_product_detail_opens(page: Page, base_url: str):
    """First product on the shop opens its detail page with purchase controls."""
    shop = ShopPage(page, base_url)
    shop.navigate()
    first_product = page.locator(
        'div#product-grid-container a[href^="/product/"]'
    ).first
    href = first_product.get_attribute("href")
    assert href

    page.goto(base_url + href)
    expect(page.locator("h1")).to_be_visible()
    expect(page.locator('button:has-text("Add to Cart")').first).to_be_visible()


def test_unknown_product_returns_404(page: Page, base_url: str):
    """Non-existent product IDs render a graceful not-found page."""
    page.goto(f"{base_url}/product/99999999")
    expect(page.locator("body")).to_contain_text("Product not found")


def test_cart_empty_state(page: Page, base_url: str):
    """Cart page shows the empty state for a fresh session."""
    page.goto(f"{base_url}/cart")
    expect(page).to_have_title("Your Cart - XCollections")
    expect(page.locator("div#cart-content")).to_be_visible()
    expect(page.locator("body")).to_contain_text("Your cart is empty")


def test_login_page_renders(page: Page, base_url: str):
    """Login page shows phone input and Send OTP button (no submit — SMS)."""
    page.goto(f"{base_url}/auth/login")
    expect(page).to_have_title("Seller Login - XCollections")
    expect(page.locator('input[name="phone"]')).to_be_visible()
    expect(page.locator('button[type="submit"]:has-text("Send OTP")')).to_be_visible()


def test_checkout_with_empty_cart_redirects(page: Page, base_url: str):
    """Checkout with an empty cart bounces back to the cart page."""
    page.goto(f"{base_url}/checkout")
    expect(page).to_have_url(re.compile(r"/cart/?$"))

"""
E2E tests for the customer direct purchase flow (Buy Now -> Checkout -> Confirmation).
"""

import pytest
from playwright.sync_api import Page, expect
from src.tests.e2e.pages.product_page import ProductPage
from src.tests.e2e.pages.checkout_page import CheckoutPage
from src.tests.e2e.pages.shop_page import ShopPage


@pytest.mark.e2e
def test_direct_buy_full_flow(page: Page, base_url: str):
    """Full journey: product detail -> Buy Now -> fill checkout form -> place order -> confirmation."""
    product_page = ProductPage(page, base_url)
    checkout_page = CheckoutPage(page, base_url)

    # 1. Product Detail
    product_id = ShopPage(page, base_url).get_product_ids(1)[0]
    product_page.navigate(product_id)
    name = product_page.get_name()
    product_page.set_quantity(2)
    product_page.click_buy_now()

    # 2. Checkout Form
    assert f"/checkout/{product_id}" in page.url
    expect(page.locator("h1")).to_contain_text("Secure Checkout")
    expect(page.locator("body")).to_contain_text(name)

    checkout_page.fill_form(
        name="Abebe Bikila",
        phone="911223344",
        address="Bole Medhanialem, Building 4, Addis Ababa",
    )
    checkout_page.place_order_and_wait()

    # 3. Confirmation Page
    assert "/order-confirmation/" in page.url
    expect(page.locator("h1")).to_contain_text("Order Confirmed")
    ref = page.url.rstrip("/").rsplit("/", 1)[-1]
    assert ref
    expect(page.locator("body")).to_contain_text(ref)
    expect(page.locator("body")).to_contain_text("Abebe Bikila")
    expect(page.locator("body")).to_contain_text("+251 911223344")


@pytest.mark.e2e
def test_checkout_invalid_phone_shows_error(page: Page, base_url: str):
    """Submitting checkout form with invalid phone number shows inline error."""
    checkout_page = CheckoutPage(page, base_url)
    product_id = ShopPage(page, base_url).get_product_ids(1)[0]
    checkout_page.navigate_direct(product_id, qty=1)

    checkout_page.fill_form(
        name="Invalid User",
        phone="12345",  # Invalid phone
        address="Near Stadium",
    )
    checkout_page.place_order()

    expect(page.locator("body")).to_contain_text("Phone number must be a valid Ethiopian number")

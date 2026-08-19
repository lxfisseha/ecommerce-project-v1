"""
E2E tests for product attribute selection and its effect on pricing.
"""

import pytest
from playwright.sync_api import Page, expect
from src.tests.e2e.pages.product_page import ProductPage
from src.tests.e2e.pages.cart_page import CartPage


@pytest.mark.e2e
def test_select_attribute_and_direct_buy_applies_extra_price(skip_hosted, page: Page, base_url: str):
    """
    Product 1 (Wireless Headphones, 2,500 ETB) has Size L costing +100 ETB.
    Selecting it and using Buy Now should total 2,500 + 100 + 150 delivery = 2,750 ETB.
    """
    product_page = ProductPage(page, base_url)
    product_page.navigate("1")

    product_page.select_attribute("Size", "L")
    product_page.click_buy_now()

    assert "/checkout/1" in page.url
    expect(page.locator("body")).to_contain_text("2,750 ETB")


@pytest.mark.e2e
def test_add_to_cart_with_attribute_shows_selection(skip_hosted, page: Page, base_url: str):
    """Adding a product with an attribute shows the selection in the cart."""
    product_page = ProductPage(page, base_url)
    product_page.navigate("1")

    product_page.select_attribute("Color", "Black")
    product_page.click_add_to_cart()

    expect(page.locator("a#cart-badge-container")).to_contain_text("1")

    cart = CartPage(page, base_url)
    cart.navigate()
    expect(page.locator("body")).to_contain_text("Color: Black")


@pytest.mark.e2e
def test_checkout_shows_attribute_total_line(skip_hosted, page: Page, base_url: str):
    """The checkout summary surfaces the attribute surcharge as its own line."""
    from src.tests.e2e.pages.checkout_page import CheckoutPage

    product_page = ProductPage(page, base_url)
    product_page.navigate("1")
    product_page.select_attribute("Size", "L")
    product_page.click_buy_now()

    expect(page.locator("body")).to_contain_text("100 ETB")
    expect(page.locator("body")).to_contain_text("2,750 ETB")

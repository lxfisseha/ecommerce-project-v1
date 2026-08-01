"""
E2E tests for customer cart management: multiple items, quantity updates,
item removal, and the empty-cart state.
"""

import pytest
from playwright.sync_api import Page, expect
from src.tests.e2e.pages.product_page import ProductPage
from src.tests.e2e.pages.cart_page import CartPage


@pytest.mark.e2e
def test_cart_with_multiple_items(page: Page, base_url: str):
    """Adding two products shows a badge count of 2 and both cart lines."""
    product_page = ProductPage(page, base_url)

    product_page.navigate("1")
    product_page.click_add_to_cart()
    product_page.navigate("4")
    product_page.click_add_to_cart()

    expect(page.locator("a#cart-badge-container")).to_contain_text("2")

    cart = CartPage(page, base_url)
    cart.navigate()
    assert cart.get_item_count() == 2
    expect(page.locator("body")).to_contain_text("Wireless Headphones")
    expect(page.locator("body")).to_contain_text("Smart Watch")


@pytest.mark.e2e
def test_cart_quantity_increment_and_decrement(page: Page, base_url: str):
    """The + / - steppers update the quantity and subtotal."""
    product_page = ProductPage(page, base_url)
    product_page.navigate("1")
    product_page.click_add_to_cart()

    cart = CartPage(page, base_url)
    cart.navigate()

    # Initial subtotal for 1x Wireless Headphones (2500) + delivery 150.
    expect(page.locator("body")).to_contain_text("2,650 ETB")

    cart.increment_quantity(0)
    expect(page.locator("body")).to_contain_text("5,150 ETB")  # 2x 2500 + 150

    cart.decrement_quantity(0)
    expect(page.locator("body")).to_contain_text("2,650 ETB")


@pytest.mark.e2e
def test_cart_remove_item_shows_empty_state(page: Page, base_url: str):
    """Removing the only item empties the cart with a friendly message."""
    product_page = ProductPage(page, base_url)
    product_page.navigate("1")
    product_page.click_add_to_cart()

    cart = CartPage(page, base_url)
    cart.navigate()
    assert cart.get_item_count() == 1

    cart.remove_item(0)
    expect(page.locator("body")).to_contain_text("Your cart is empty")
    assert cart.is_empty()


@pytest.mark.e2e
def test_empty_cart_checkout_redirects_to_cart(page: Page, base_url: str):
    """Visiting /checkout with an empty cart bounces back to /cart."""
    page.goto("/checkout")

    expect(page).to_have_url(base_url + "/cart")
    expect(page.locator("body")).to_contain_text("Your cart is empty")

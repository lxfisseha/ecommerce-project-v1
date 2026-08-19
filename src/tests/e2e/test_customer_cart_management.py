"""
E2E tests for customer cart management: multiple items, quantity updates,
item removal, and the empty-cart state.
"""

import pytest
from playwright.sync_api import Page, expect
from src.tests.e2e.pages.product_page import ProductPage
from src.tests.e2e.pages.cart_page import CartPage
from src.tests.e2e.pages.shop_page import ShopPage


@pytest.mark.e2e
def test_cart_with_multiple_items(page: Page, base_url: str):
    """Adding two products shows a badge count of 2 and both cart lines."""
    ids = ShopPage(page, base_url).get_product_ids(2)
    assert len(ids) == 2

    product_page = ProductPage(page, base_url)
    product_page.navigate(ids[0])
    name0 = product_page.get_name()
    product_page.click_add_to_cart()
    product_page.navigate(ids[1])
    name1 = product_page.get_name()
    product_page.click_add_to_cart()

    expect(page.locator("a#cart-badge-container")).to_contain_text("2")

    cart = CartPage(page, base_url)
    cart.navigate()
    assert cart.get_item_count() == 2
    expect(page.locator("body")).to_contain_text(name0)
    expect(page.locator("body")).to_contain_text(name1)


@pytest.mark.e2e
def test_cart_quantity_increment_and_decrement(page: Page, base_url: str):
    """The + / - steppers update the quantity and subtotal."""
    ids = ShopPage(page, base_url).get_product_ids(1)
    product_page = ProductPage(page, base_url)
    product_page.navigate(ids[0])
    price = product_page.get_price()
    product_page.click_add_to_cart()

    cart = CartPage(page, base_url)
    cart.navigate()

    # Total = 1x price + 150 ETB fixed delivery fee.
    expect(page.locator("body")).to_contain_text(f"{price + 150:,} ETB")

    cart.increment_quantity(0)
    expect(page.locator("body")).to_contain_text(f"{2 * price + 150:,} ETB")

    cart.decrement_quantity(0)
    expect(page.locator("body")).to_contain_text(f"{price + 150:,} ETB")


@pytest.mark.e2e
def test_cart_remove_item_shows_empty_state(page: Page, base_url: str):
    """Removing the only item empties the cart with a friendly message."""
    ids = ShopPage(page, base_url).get_product_ids(1)
    product_page = ProductPage(page, base_url)
    product_page.navigate(ids[0])
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

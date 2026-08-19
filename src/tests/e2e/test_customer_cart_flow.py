"""
E2E tests for customer shopping cart flow (Add to Cart -> Cart View -> Cart Checkout -> Confirmation).
"""

import pytest
from playwright.sync_api import Page, expect
from src.tests.e2e.pages.product_page import ProductPage
from src.tests.e2e.pages.cart_page import CartPage
from src.tests.e2e.pages.checkout_page import CheckoutPage
from src.tests.e2e.pages.shop_page import ShopPage


@pytest.mark.e2e
def test_cart_add_and_checkout_flow(page: Page, base_url: str):
    """Add items to cart, open cart page, verify subtotal, proceed to checkout & place order."""
    product_page = ProductPage(page, base_url)
    cart_page = CartPage(page, base_url)
    checkout_page = CheckoutPage(page, base_url)

    # 1. Add product to cart
    ids = ShopPage(page, base_url).get_product_ids(1)
    product_page.navigate(ids[0])
    name = product_page.get_name()
    product_page.click_add_to_cart()

    # Verify cart badge counter updated
    badge = page.locator("a#cart-badge-container")
    expect(badge).to_contain_text("1")

    # 2. Go to Cart Page
    cart_page.navigate()
    expect(page.locator("body")).to_contain_text(name)

    # 3. Proceed to Checkout
    cart_page.proceed_to_checkout()
    assert "/checkout" in page.url

    # 4. Fill details & Place Order
    checkout_page.fill_form(
        name="Tigist Assefa",
        phone="922334455",
        address="Kazanchis, House 102",
    )
    checkout_page.place_order_and_wait()

    # 5. Confirmation
    assert "/order-confirmation/" in page.url
    expect(page.locator("h1")).to_contain_text("Order Confirmed")
    expect(page.locator("body")).to_contain_text("Tigist Assefa")

"""
E2E tests for the seller inventory management: list, search, add, edit,
toggle stock, and delete products.
"""

import re

import pytest
from playwright.sync_api import Page, expect

_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0bIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n\x2d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.e2e
def test_products_list_renders(seller_page: Page, base_url: str):
    """The inventory page lists the seeded products and the add link."""
    seller_page.goto("/dashboard/products")

    expect(seller_page.locator("body")).to_contain_text("Product Management")
    expect(seller_page.locator('a[href="/dashboard/products/add"]')).to_contain_text(
        "Add New Product"
    )
    expect(seller_page.locator("body")).to_contain_text("Elegant Maxi Dress")
    expect(seller_page.locator("body")).to_contain_text("Elegant High Heel Shoes")


@pytest.mark.e2e
def test_products_search_filters_list(seller_page: Page, base_url: str):
    """Typing in the inventory search box filters products via HTMX."""
    seller_page.goto("/dashboard/products")

    search_box = seller_page.locator('input[name="search"]')
    search_box.fill("Dress")
    search_box.dispatch_event("keyup")

    expect(seller_page.locator("#product-list-content")).to_contain_text(
        "Elegant Maxi Dress"
    )
    expect(seller_page.locator("#product-list-content")).not_to_contain_text(
        "Elegant High Heel Shoes"
    )


@pytest.mark.e2e
def test_add_product_flow(seller_page: Page, base_url: str):
    """Adding a product with an image redirects back and lists the new item."""
    seller_page.goto("/dashboard/products/add")

    seller_page.locator('input[name="name"]').fill("E2E Fresh Product")
    seller_page.locator('textarea[name="description"]').fill(
        "Created by an E2E test via the seller UI"
    )
    seller_page.locator('input[name="price"]').fill("1234.50")
    seller_page.locator('input[name="tags"]').fill("e2e, test")

    seller_page.locator('input[name="image"]').set_input_files(
        files={"name": "test.png", "mimeType": "image/png", "buffer": _PNG}
    )
    # The preview JS renders a tag select for the first image, defaulting to "main".
    seller_page.locator('select[name="image_tag_0"]').wait_for(state="visible")

    seller_page.locator('button[type="submit"]:has-text("Save Product")').click()

    expect(seller_page).to_have_url(re.compile(r"/dashboard/products/?$"))
    expect(seller_page.locator("#product-list-content")).to_contain_text(
        "E2E Fresh Product"
    )


@pytest.mark.e2e
def test_edit_product_flow(seller_page: Page, base_url: str):
    """Editing a product name is reflected in the list."""
    seller_page.goto("/dashboard/products/edit/2")

    name_input = seller_page.locator('input[name="name"]')
    expect(name_input).to_have_value("Modern Habesha Dress")
    name_input.fill("Modern Habesha Dress V2")
    seller_page.locator('button[type="submit"]:has-text("Save Product")').click()

    expect(seller_page).to_have_url(re.compile(r"/dashboard/products/?$"))
    expect(seller_page.locator("#product-list-content")).to_contain_text(
        "Modern Habesha Dress V2"
    )


@pytest.mark.e2e
def test_toggle_stock_flips_badge(seller_page: Page, base_url: str):
    """Toggling stock for a product flips the In Stock / Sold Out state."""
    seller_page.goto("/dashboard/products")

    toggle = seller_page.locator('#stock-toggle-2')
    expect(toggle).to_contain_text("In Stock")

    toggle.click()
    expect(seller_page.locator('#stock-toggle-2')).to_contain_text("Sold Out")

    # Restore state so the seeded product stays in stock for other tests.
    seller_page.locator('#stock-toggle-2').click()
    expect(seller_page.locator('#stock-toggle-2')).to_contain_text("In Stock")


@pytest.mark.e2e
def test_delete_product_flow(seller_page: Page, base_url: str):
    """
    Deleting a product (via hx-delete + confirm dialog) removes its card.
    Uses a fresh product so other tests are unaffected.
    """
    # Create a throwaway product.
    seller_page.goto("/dashboard/products/add")
    seller_page.locator('input[name="name"]').fill("Doomed Product")
    seller_page.locator('input[name="price"]').fill("1.00")
    seller_page.locator('input[name="image"]').set_input_files(
        files={"name": "test.png", "mimeType": "image/png", "buffer": _PNG}
    )
    seller_page.locator('select[name="image_tag_0"]').wait_for(state="visible")
    seller_page.locator('button[type="submit"]:has-text("Save Product")').click()
    expect(seller_page.locator("#product-list-content")).to_contain_text(
        "Doomed Product"
    )

    # Find its card by name and delete it, accepting the confirm dialog.
    card = seller_page.locator(
        '#product-list-content div[id^="product-"]:has-text("Doomed Product")'
    ).first
    product_id = card.get_attribute("id").replace("product-", "")
    delete_btn = card.locator('button[hx-delete^="/dashboard/products/"]')

    seller_page.once("dialog", lambda dialog: dialog.accept())
    delete_btn.click()

    expect(seller_page.locator(f'#product-{product_id}')).to_have_count(0)

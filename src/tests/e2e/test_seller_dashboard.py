"""
E2E tests for the seller dashboard: stats, orders list, order status workflow,
and profile updates.
"""

import re

import pytest
from playwright.sync_api import Page, expect
from src.tests.e2e.pages.checkout_page import CheckoutPage


def _place_order(page: Page, base_url: str) -> str:
    """
    Create a single order via the buyer direct-buy flow and return its
    ET-... reference captured from the confirmation URL.
    """
    checkout = CheckoutPage(page, base_url)
    checkout.navigate_direct("1", qty=1)
    checkout.fill_form(
        name="Seller Flow Buyer",
        phone="933445566",
        address="Piassa, House 77, Addis Ababa",
    )
    checkout.place_order_and_wait()

    assert "/order-confirmation/" in page.url
    ref = page.url.rsplit("/", 1)[-1]
    assert ref.startswith("ET-")
    return ref


@pytest.mark.e2e
def test_dashboard_renders_stats(seller_page: Page, base_url: str):
    """Dashboard shows the seller welcome and stat cards."""
    seller_page.goto("/dashboard")

    expect(seller_page.locator("body")).to_contain_text("Welcome back, Test Seller")
    expect(seller_page.locator("body")).to_contain_text("Total Orders")
    expect(seller_page.locator("body")).to_contain_text("Total Sales")
    expect(seller_page.locator("body")).to_contain_text("Pending")
    expect(seller_page.locator("body")).to_contain_text("Active Products")
    expect(seller_page.locator("body")).to_contain_text("Recent Orders")


@pytest.mark.e2e
def test_orders_list_and_status_filters(seller_page: Page, base_url: str):
    """Orders page shows the management header and status filter tabs."""
    seller_page.goto("/dashboard/orders")

    expect(seller_page.locator("body")).to_contain_text("Order Management")
    for tab in ("pending", "shipped", "completed"):
        expect(seller_page.locator(f'a[href*="status={tab}"]')).to_be_visible()
    expect(seller_page.locator('div a[href="/dashboard/orders"]').first).to_be_visible()


@pytest.mark.e2e
def test_order_status_workflow(page: Page, seller_page: Page, base_url: str):
    """
    Place an order as a buyer, then as the seller: view it, mark it shipped,
    mark it completed, and confirm the terminal state locks further changes.
    """
    ref = _place_order(page, base_url)

    # Seller views the order from the orders list.
    seller_page.goto("/dashboard/orders")
    expect(seller_page.locator("body")).to_contain_text(ref)

    seller_page.locator(f"tr:has-text('{ref}') a[href*='/dashboard/orders/']").click()
    expect(seller_page).to_have_url(re.compile(r"/dashboard/orders/\d+"))

    expect(seller_page.locator("body")).to_contain_text("Seller Flow Buyer")
    expect(seller_page.locator("body")).to_contain_text("Elegant Maxi Dress")
    expect(seller_page.locator("button[type='submit'][value='shipped']")).to_be_visible()

    # pending -> shipped
    seller_page.locator("button[type='submit'][value='shipped']").click()
    expect(seller_page.locator("body")).to_contain_text("Shipped")
    expect(seller_page.locator("body")).to_contain_text("Mark as Completed")

    # shipped -> completed
    seller_page.locator("button[type='submit'][value='completed']").click()
    expect(seller_page.locator("body")).to_contain_text("Completed")
    expect(seller_page.locator("body")).to_contain_text(
        "cannot be modified"
    )


@pytest.mark.e2e
def test_seller_profile_update(seller_page: Page, base_url: str):
    """Seller can update profile details and sees the success message."""
    seller_page.goto("/dashboard/profile")

    expect(seller_page.locator("body")).to_contain_text("Seller Profile")

    address_input = seller_page.locator('input[name="business_address"]')
    address_input.fill("Bole Medhanialem, Addis Ababa")
    seller_page.locator('button[type="submit"]:has-text("Save All Changes")').click()

    expect(seller_page.locator("body")).to_contain_text("Profile updated successfully!")
    expect(seller_page.locator('input[name="business_address"]')).to_have_value(
        "Bole Medhanialem, Addis Ababa"
    )

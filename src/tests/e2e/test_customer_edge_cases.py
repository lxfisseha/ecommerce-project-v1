"""
E2E tests for customer side edge cases, error handling, and 404 pages.
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_nonexistent_product_404(page: Page, base_url: str):
    """Navigating to non-existent product ID renders error page or 404 status."""
    response = page.goto(f"{base_url}/product/999999")
    assert response.status == 404


@pytest.mark.e2e
def test_nonexistent_order_confirmation_404(page: Page, base_url: str):
    """Navigating directly to invalid order reference renders 404/403."""
    response = page.goto(f"{base_url}/order-confirmation/INVALID-REF-1234")
    assert response.status in (403, 404)


@pytest.mark.e2e
def test_support_page_loads(page: Page, base_url: str):
    """Support page renders correctly with merchant info."""
    page.goto(f"{base_url}/support")
    expect(page.locator("body")).to_contain_text("Support")

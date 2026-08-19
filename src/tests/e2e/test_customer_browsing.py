"""
E2E tests for customer browsing, searching, filtering, and sorting.
"""

import pytest
from playwright.sync_api import Page, expect
from src.tests.e2e.pages.home_page import HomePage
from src.tests.e2e.pages.shop_page import ShopPage
from src.tests.e2e.pages.product_page import ProductPage


@pytest.mark.e2e
def test_homepage_loads_with_products(page: Page, base_url: str):
    """Customer lands on homepage, sees hero, products grid, and navigation."""
    home = HomePage(page, base_url)
    home.navigate()

    expect(page).to_have_title("Welcome to XCollections")
    expect(page.locator("h1")).to_contain_text("Discover women's fashion")

    # Check navigation links
    nav_links = home.get_nav_links()
    expect(nav_links["logo"]).to_be_visible()
    expect(nav_links["shop"]).to_be_visible()

    # Check products rendered on homepage
    cards = home.get_product_cards()
    expect(cards.first).to_be_visible()
    assert cards.count() > 0


@pytest.mark.e2e
def test_homepage_search_navigates_to_shop(page: Page, base_url: str):
    """Searching on homepage hero redirects to /shop?q=... with filtered products."""
    home = HomePage(page, base_url)
    home.navigate()

    home.search("Dress")

    assert "/shop" in page.url
    assert "q=Dress" in page.url
    expect(page.locator("div#product-grid-container")).to_contain_text("Dress")


@pytest.mark.e2e
def test_shop_page_displays_grid_and_search(page: Page, base_url: str):
    """Shop page renders product grid, search input works via HTMX."""
    shop = ShopPage(page, base_url)
    shop.navigate()

    expect(page.locator("div#product-grid-container")).to_be_visible()
    initial_count = shop.get_product_count()
    assert initial_count > 0

    # Perform HTMX search
    shop.search("Dress")
    expect(page.locator("div#product-grid-container")).to_contain_text("Dress")


@pytest.mark.e2e
def test_shop_tag_filtering(page: Page, base_url: str):
    """Clicking a tag filter updates the product catalog."""
    shop = ShopPage(page, base_url)
    shop.navigate()

    shop.filter_by_tag("shoes")
    expect(page.locator("div#product-grid-container")).to_contain_text("Shoes")


@pytest.mark.e2e
def test_shop_sort_by_price(page: Page, base_url: str):
    """Selecting price-low sort orders products by ascending price."""
    import re
    shop = ShopPage(page, base_url)
    shop.navigate()

    def prices() -> list[int]:
        texts = [el.inner_text() for el in page.locator("div#product-grid-container span.text-accent").all()]
        return [int(m.group(1).replace(",", "")) for m in (re.search(r"([\d,]+)\s*ETB", t) for t in texts) if m]

    shop.sort_by("price-low")
    sorted_prices = prices()
    assert len(sorted_prices) > 0
    assert sorted_prices == sorted(sorted_prices)


@pytest.mark.e2e
def test_shop_hides_out_of_stock(page: Page, base_url: str):
    """Out of stock products do not appear in buyer shop."""
    shop = ShopPage(page, base_url)
    shop.navigate()

    expect(page.locator("div#product-grid-container")).not_to_contain_text("Sold Out Gadget")


@pytest.mark.e2e
def test_product_detail_page(page: Page, base_url: str):
    """Clicking a product takes customer to detail view with title, price, and controls."""
    shop = ShopPage(page, base_url)
    shop.navigate()
    href = shop.page.locator('div#product-grid-container a[href^="/product/"]').first.get_attribute("href")
    assert href

    product_page = ProductPage(page, base_url)
    product_page.navigate(href.split("/")[-1])

    expect(page.locator("h1")).to_be_visible()
    expect(page.locator("body")).to_contain_text("ETB")

    # Set quantity
    product_page.set_quantity(3)
    expect(page.locator("input#quantity")).to_have_value("3")


@pytest.mark.e2e
def test_shop_pagination_shows_second_page(page: Page, base_url: str):
    """With 25 in-stock products, the shop shows a second page."""
    shop = ShopPage(page, base_url)
    shop.navigate()

    shop.go_to_page(2)
    assert "page=2" in page.url
    expect(page.locator("div#product-grid-container")).to_be_visible()


@pytest.mark.e2e
def test_homepage_shop_all_navigates_to_shop(page: Page, base_url: str):
    """The homepage 'Shop All' link leads to the full shop grid."""
    home = HomePage(page, base_url)
    home.navigate()
    home.click_shop_all()

    assert "/shop" in page.url
    expect(page.locator("div#product-grid-container")).to_be_visible()


@pytest.mark.e2e
def test_out_of_stock_product_is_not_viewable(page: Page, base_url: str):
    """An out-of-stock product's detail page is not reachable by buyers."""
    page.goto(f"{base_url}/product/99999999")

    expect(page.locator("body")).to_contain_text("Product not found")
    expect(page.locator("body")).not_to_contain_text("Sold Out Gadget")

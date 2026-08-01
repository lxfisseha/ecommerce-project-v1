from playwright.sync_api import Page, Locator

class HomePage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def navigate(self) -> None:
        self.page.goto(self.base_url + "/")

    def search(self, query: str) -> None:
        form = self.page.locator('form[action="/shop"][method="GET"]')
        form.locator('input[name="q"]').fill(query)
        form.locator('button[type="submit"], input[type="submit"]').first.click()
        self.page.wait_for_load_state('networkidle')

    def get_product_cards(self) -> Locator:
        # Assuming product cards have a consistent class in the _product_grid.html partial
        # We can also return locators that have the add to cart or product link
        return self.page.locator('a[href^="/product/"]')

    def click_shop_all(self) -> None:
        self.page.locator('a[href="/shop"]').first.click()
        self.page.wait_for_load_state('networkidle')

    def get_nav_links(self) -> dict[str, Locator]:
        return {
            "logo": self.page.locator('a[href="/"]').first,
            "shop": self.page.locator('a[href="/shop"]').first,
            "support": self.page.locator('a[href="/support"]').first,
        }

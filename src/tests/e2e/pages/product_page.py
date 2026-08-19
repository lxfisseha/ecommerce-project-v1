from playwright.sync_api import Page

class ProductPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def navigate(self, product_id: str) -> None:
        self.page.goto(f"{self.base_url}/product/{product_id}")

    def get_name(self) -> str:
        return self.page.locator('h1').first.inner_text().strip()

    def get_price(self) -> int:
        # The main price on the detail page contains "ETB" (the header logo's
        # text-accent span does not).
        import re
        text = self.page.locator('span.text-accent:has-text("ETB")').first.inner_text()
        m = re.search(r"([\d,]+)", text)
        assert m, f"Could not parse price from: {text!r}"
        return int(m.group(1).replace(",", ""))

    def set_quantity(self, n: int) -> None:
        # The quantity input is readonly (desktop + mobile sticky bars each render
        # it); drive it with the visible "+" stepper button instead of fill().
        plus = self.page.locator('button[onclick="updateQty(1)"]:visible').first
        for _ in range(n - 1):
            plus.click()

    def select_attribute(self, attr_type: str, value: str) -> None:
        self.page.locator(f'div.attribute-group[data-type="{attr_type}"] button.attr-btn:has-text("{value}")').first.click()

    def click_buy_now(self) -> None:
        # The page renders two "Buy Now" buttons (desktop + mobile sticky bar);
        # the mobile one is hidden (lg:hidden) at the test viewport.
        self.page.locator('button[onclick="goToCheckout()"]:visible').first.click()
        self.page.wait_for_load_state('networkidle')

    def click_add_to_cart(self) -> None:
        # Same as click_buy_now — two matching buttons exist (desktop + mobile).
        self.page.locator('button[hx-post^="/cart/add/"]:visible').first.click()
        self.page.wait_for_load_state('networkidle')

    def get_cart_badge_count(self) -> int:
        badge_text = self.page.locator('a#cart-badge-container').inner_text().strip()
        try:
            return int(badge_text) if badge_text else 0
        except ValueError:
            return 0

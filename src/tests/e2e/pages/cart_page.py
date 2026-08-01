from typing import List
from playwright.sync_api import Page

class CartPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def navigate(self) -> None:
        self.page.goto(self.base_url + "/cart")

    def get_item_count(self) -> int:
        return self.page.locator('div[id^="cart-line-"]').count()

    def get_item_names(self) -> List[str]:
        locators = self.page.locator('div[id^="cart-line-"] .product-name, div[id^="cart-line-"] h3').all()
        return [loc.inner_text().strip() for loc in locators]

    def increment_quantity(self, index: int) -> None:
        # Assumes buttons might have +/- text or we can click based on value
        # The prompt says: increment with value qty+1
        # E.g. find the cart-line and click its increment button
        line = self.page.locator(f'div#cart-line-{index}')
        line.locator('button[type="submit"][name="qty"]').last.click()
        self.page.wait_for_load_state('networkidle')

    def decrement_quantity(self, index: int) -> None:
        line = self.page.locator(f'div#cart-line-{index}')
        line.locator('button[type="submit"][name="qty"]').first.click()
        self.page.wait_for_load_state('networkidle')

    def remove_item(self, index: int) -> None:
        self.page.locator(f'button[hx-post="/cart/remove/{index}"][hx-target="#cart-content"]').click()
        self.page.wait_for_load_state('networkidle')

    def get_total(self) -> str:
        return self.page.locator('.cart-total, [data-testid="cart-total"]').first.inner_text().strip()

    def proceed_to_checkout(self) -> None:
        self.page.locator('a[href="/checkout"]').first.click()
        self.page.wait_for_load_state('networkidle')

    def is_empty(self) -> bool:
        # Assuming there is a text like "Your cart is empty" or no cart lines
        return self.get_item_count() == 0

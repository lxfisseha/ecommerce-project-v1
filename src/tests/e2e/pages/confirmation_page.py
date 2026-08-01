from playwright.sync_api import Page

class ConfirmationPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def get_order_reference(self) -> str:
        return self.page.locator('.order-reference, [data-testid="order-reference"]').first.inner_text().strip()

    def get_order_status(self) -> str:
        return self.page.locator('.order-status, [data-testid="order-status"]').first.inner_text().strip()

    def get_buyer_name(self) -> str:
        return self.page.locator('.buyer-name, [data-testid="buyer-name"]').first.inner_text().strip()

    def get_total_paid(self) -> str:
        return self.page.locator('.total-paid, [data-testid="total-paid"]').first.inner_text().strip()

    def click_continue_shopping(self) -> None:
        self.page.locator('a[href="/"]').first.click()
        self.page.wait_for_load_state('networkidle')

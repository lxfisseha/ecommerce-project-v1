import urllib.parse
from playwright.sync_api import Page

class CheckoutPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def navigate_direct(self, product_id: str, qty: int = 1, attrs: str = None) -> None:
        params = {"qty": str(qty)}
        if attrs:
            params["attrs"] = attrs
        
        url = f"{self.base_url}/checkout/{product_id}?" + urllib.parse.urlencode(params)
        self.page.goto(url)

    def navigate_cart(self) -> None:
        self.page.goto(self.base_url + "/checkout")

    def fill_form(self, name: str, phone: str, address: str) -> None:
        self.page.locator('input#buyer_name[name="buyer_name"]').fill(name)
        self.page.locator('input#buyer_phone[name="buyer_phone"][type="tel"]').fill(phone)
        self.page.locator('textarea#delivery_address[name="delivery_address"]').fill(address)

    def get_order_total(self) -> str:
        return self.page.locator('.order-total, [data-testid="order-total"]').first.inner_text().strip()

    def place_order(self) -> None:
        self.page.locator('button[type="submit"]:has-text("Place Order")').click()
        self.page.wait_for_load_state('networkidle')

    def get_error_message(self) -> str:
        error_loc = self.page.locator('.error-message, .invalid-feedback')
        if error_loc.count() > 0:
            return error_loc.first.inner_text().strip()
        return ""

    def get_product_name(self) -> str:
        return self.page.locator('.summary-product-name').first.inner_text().strip()

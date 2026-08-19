import urllib.parse
from typing import Union, List
from playwright.sync_api import Page

class ShopPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def navigate(self, query: str = None, sort_by: str = None, tag: str = None, page_num: int = None) -> None:
        params = {}
        if query: params['q'] = query
        if sort_by: params['sort_by'] = sort_by
        if tag: params['tag'] = tag
        if page_num: params['page'] = str(page_num)
        
        url = self.base_url + "/shop"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        self.page.goto(url)

    def search(self, query: str) -> None:
        search_box = self.page.locator('input#search-input[name="q"]')
        search_box.fill(query)
        # The input filters via HTMX on `keyup changed delay:500ms`; fill() only
        # emits `input`, so dispatch the keyup to trigger the request.
        search_box.dispatch_event("keyup")
        self.page.wait_for_load_state('networkidle')

    def sort_by(self, option: str) -> None:
        self.page.locator('select#sort-dropdown[name="sort_by"]').select_option(option)
        self.page.wait_for_load_state('networkidle')

    def filter_by_tag(self, tag: str) -> None:
        self.page.locator(f'button[hx-get*="/shop?tag={tag}"]').first.click()
        self.page.wait_for_load_state('networkidle')

    def get_product_names(self) -> List[str]:
        # Based on generic assumption for product names. Adjust as per actual HTML inside div#product-grid-container
        locators = self.page.locator('div#product-grid-container h3, div#product-grid-container .product-title').all()
        return [loc.inner_text().strip() for loc in locators]

    def get_product_count(self) -> int:
        return self.page.locator('div#product-grid-container a[href^="/product/"]').count()

    def get_product_ids(self, count: int = 1) -> List[str]:
        """Return up to `count` product ids from the first shop page."""
        self.navigate()
        ids: List[str] = []
        for link in self.page.locator('div#product-grid-container a[href^="/product/"]').all()[:count]:
            href = link.get_attribute("href")
            if href:
                ids.append(href.split("/")[-1])
        return ids

    def click_product(self, name_or_index: Union[str, int]) -> None:
        if isinstance(name_or_index, int):
            self.page.locator('div#product-grid-container a[href^="/product/"]').nth(name_or_index).click()
        else:
            self.page.locator(f'div#product-grid-container a[href^="/product/"]:has-text("{name_or_index}")').first.click()
        self.page.wait_for_load_state('networkidle')

    def go_to_page(self, n: int) -> None:
        # Pagination buttons are hx-get triggers (not links); hx-push-url updates the URL.
        self.page.locator(f'button[hx-get*="page={n}"]').first.click()
        self.page.wait_for_load_state('networkidle')

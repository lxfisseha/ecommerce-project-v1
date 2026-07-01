import pytest_asyncio
from src.tests.conftest import client, maker, get_csrf_context


@pytest_asyncio.fixture
async def seeded_product():
    from src.features.products.models import Product
    async with maker() as session:
        p = Product(id=99, seller_id=1, name="Test", price=50.0, in_stock=True)
        session.add(p)
        await session.commit()


class TestCheckoutValidation:

    @pytest_asyncio.fixture(autouse=True)
    async def _setup(self, seeded_product):
        self.token, self.csrf_cookie = get_csrf_context(client)

    def _post(self, data):
        return client.post(
            "/checkout/99",
            data=data,
            cookies={"csrftoken": self.csrf_cookie},
            headers={"X-CSRF-Token": self.token}
        )

    def test_missing_name(self):
        resp = self._post({"buyer_phone": "0912345678", "delivery_address": "Addr", "quantity": "1"})
        assert resp.status_code == 422

    def test_missing_address(self):
        resp = self._post({"buyer_name": "Buyer", "buyer_phone": "0912345678", "quantity": "1"})
        assert resp.status_code == 422

    def test_invalid_phone_returns_checkout_page(self):
        resp = self._post({"buyer_name": "Buyer", "buyer_phone": "123", "delivery_address": "Addr", "quantity": "1"})
        assert resp.status_code == 200

    def test_missing_csrf(self):
        resp = client.post("/checkout/99", data={"buyer_name": "Buyer", "buyer_phone": "0912345678", "delivery_address": "Addr", "quantity": "1"})
        assert resp.status_code == 403

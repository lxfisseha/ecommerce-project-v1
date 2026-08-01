import pytest
import pytest_asyncio
from decimal import Decimal
from sqlmodel import select
from sqlalchemy.orm import selectinload
from src.features.products.models import Product, ProductAttribute
from src.features.orders.models import Order, OrderItem
from src.tests.conftest import client, maker, get_csrf_context


@pytest_asyncio.fixture(autouse=True)
async def seed_cart_products():
    async with maker() as session:
        session.add_all(
            [
                Product(id=1, seller_id=1, name="Cart Product A", description="A",
                        price=Decimal("500.00"), in_stock=True),
                Product(id=2, seller_id=1, name="Cart Product B", description="B",
                        price=Decimal("200.00"), in_stock=True),
            ]
        )
        await session.commit()


@pytest.fixture(autouse=True)
def clean_client_cookies():
    """Isolate session (cart + csrf cookies) between tests."""
    client.cookies.clear()
    yield
    client.cookies.clear()


def _csrf():
    token, _ = get_csrf_context(client)
    return token


def _add(product_id, qty=1, attrs="", token=None):
    token = token or _csrf()
    return client.post(
        f"/cart/add/{product_id}",
        data={"qty": str(qty), "attributes": attrs},
        headers={"X-CSRF-Token": token},
    )


@pytest.mark.asyncio
async def test_add_to_cart_updates_badge():
    token = _csrf()
    resp = _add(1, qty=2, attrs="Size: L", token=token)
    assert resp.status_code == 200
    assert "2" in resp.text  # badge count

    # Adding the same product + attributes again merges quantities
    resp2 = _add(1, qty=1, attrs="Size: L", token=token)
    assert "3" in resp2.text


@pytest.mark.asyncio
async def test_same_product_different_attributes_stay_separate():
    token = _csrf()
    _add(1, qty=1, attrs="Color: Red", token=token)
    _add(1, qty=1, attrs="Color: Blue", token=token)

    resp = client.get("/cart")
    assert resp.status_code == 200
    assert "Color: Red" in resp.text
    assert "Color: Blue" in resp.text


@pytest.mark.asyncio
async def test_cart_page_renders_items_and_totals():
    token = _csrf()
    _add(1, qty=1, token=token)
    _add(2, qty=3, token=token)

    resp = client.get("/cart")
    assert resp.status_code == 200
    assert "Cart Product A" in resp.text
    assert "Cart Product B" in resp.text
    assert 'id="cart-content"' in resp.text
    assert "htmx-indicator" in resp.text
    # subtotal = 500 + 3*200 = 1100; delivery 150; total 1250
    assert "1,100" in resp.text
    assert "1,250" in resp.text


@pytest.mark.asyncio
async def test_cart_update_and_remove():
    token = _csrf()
    _add(1, qty=2, token=token)

    resp = client.post(
        "/cart/update/0", data={"qty": "5"}, headers={"X-CSRF-Token": token}
    )
    assert resp.status_code == 200
    assert 'id="cart-content"' in resp.text
    assert "2,500" in resp.text  # 500 * 5

    resp2 = client.post(
        "/cart/remove/0", data={}, headers={"X-CSRF-Token": token}
    )
    assert resp2.status_code == 200
    assert 'id="cart-content"' in resp2.text
    assert "Your cart is empty" in resp2.text


@pytest.mark.asyncio
async def test_cart_checkout_creates_single_order_with_items():
    token = _csrf()
    _add(1, qty=2, attrs="Size: L", token=token)
    _add(2, qty=1, token=token)

    resp = client.post(
        "/checkout",
        data={
            "buyer_name": "Cart Buyer",
            "buyer_phone": "0912345678",
            "delivery_address": "Bole, Addis Ababa",
            "csrf_token": token,
        },
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith("/order-confirmation/ET-TEST-")

    confirm = client.get(location)
    assert confirm.status_code == 200
    assert "Cart Product A" in confirm.text
    assert "Cart Product B" in confirm.text

    async with maker() as session:
        stmt = (
            select(Order)
            .where(Order.buyer_name == "Cart Buyer")
            .options(selectinload(Order.items))
        )
        order = (await session.execute(stmt)).scalar_one_or_none()
        assert order is not None
        assert len(order.items) == 2
        assert order.delivery_fee == Decimal("150.00")
        assert order.subtotal == Decimal("1200.00")  # 2*500 + 200
        assert order.total_amount == Decimal("1350.00")
        assert {i.product_name for i in order.items} == {
            "Cart Product A",
            "Cart Product B",
        }
        assert all(isinstance(i, OrderItem) for i in order.items)


@pytest.mark.asyncio
async def test_cart_checkout_with_attribute_surcharge():
    async with maker() as session:
        attr = ProductAttribute(
            product_id=1, attribute_type="Color", attribute_value="Red",
            extra_price=Decimal("100.00"),
        )
        session.add(attr)
        await session.commit()

    token = _csrf()
    _add(1, qty=2, attrs="Color: Red", token=token)

    resp = client.get("/cart")
    assert resp.status_code == 200
    # line subtotal = (500 + 100) * 2 = 1200; total = 1350
    assert "1,200" in resp.text
    assert "1,350" in resp.text

    post = client.post(
        "/checkout",
        data={
            "buyer_name": "Attr Buyer",
            "buyer_phone": "0911223344",
            "delivery_address": "Merkato",
            "csrf_token": token,
        },
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert post.status_code == 303

    async with maker() as session:
        stmt = (
            select(Order)
            .where(Order.buyer_name == "Attr Buyer")
            .options(selectinload(Order.items))
        )
        order = (await session.execute(stmt)).scalar_one_or_none()
        assert order is not None
        assert order.items[0].attributes_selected == "Color: Red"
        assert order.items[0].subtotal == Decimal("1200.00")
        assert order.total_amount == Decimal("1350.00")


@pytest.mark.asyncio
async def test_cart_cleared_after_checkout():
    token = _csrf()
    _add(1, qty=1, token=token)

    client.post(
        "/checkout",
        data={
            "buyer_name": "Cleared Buyer",
            "buyer_phone": "0912345678",
            "delivery_address": "Bole",
            "csrf_token": token,
        },
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )

    resp = client.get("/cart")
    assert "Your cart is empty" in resp.text


@pytest.mark.asyncio
async def test_cart_checkout_page_renders_items():
    token = _csrf()
    _add(1, qty=1, token=token)
    _add(2, qty=2, token=token)

    resp = client.get("/checkout")
    assert resp.status_code == 200
    assert "Secure Checkout" in resp.text
    assert "Cart Product A" in resp.text
    assert "Cart Product B" in resp.text
    # subtotal = 500 + 2*200 = 900; delivery 150; total 1050
    assert "900" in resp.text
    assert "1,050" in resp.text
    # form posts to the cart-based checkout
    assert 'action="/checkout"' in resp.text


@pytest.mark.asyncio
async def test_empty_cart_checkout_redirects_to_cart():
    token = _csrf()
    resp = client.post(
        "/checkout",
        data={
            "buyer_name": "Nobody",
            "buyer_phone": "0912345678",
            "delivery_address": "Bole",
            "csrf_token": token,
        },
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/cart"


@pytest.mark.asyncio
async def test_out_of_stock_item_pruned_from_cart():
    token = _csrf()
    _add(1, qty=1, token=token)

    async with maker() as session:
        product = await session.get(Product, 1)
        product.in_stock = False
        await session.commit()

    resp = client.get("/cart")
    assert resp.status_code == 200
    assert "Your cart is empty" in resp.text

    checkout = client.post(
        "/checkout",
        data={
            "buyer_name": "Pruned Buyer",
            "buyer_phone": "0912345678",
            "delivery_address": "Bole",
            "csrf_token": token,
        },
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert checkout.status_code == 303
    assert checkout.headers["location"] == "/cart"


@pytest.mark.asyncio
async def test_cart_posts_require_csrf():
    resp = client.post(
        "/cart/add/1", data={"qty": "1", "attributes": ""}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cart_badge_present_across_pages():
    home = client.get("/")
    assert home.status_code == 200
    assert "cart-badge-container" in home.text

    shop = client.get("/shop")
    assert shop.status_code == 200
    assert "cart-badge-container" in shop.text


@pytest.mark.asyncio
async def test_product_detail_offers_add_to_cart_and_buy_now():
    resp = client.get("/product/1")
    assert resp.status_code == 200
    assert "Add to Cart" in resp.text
    assert "Buy Now" in resp.text


@pytest.mark.asyncio
async def test_product_detail_add_to_cart_hx_vals_are_valid():
    resp = client.get("/product/1")
    assert resp.status_code == 200
    # htmx only evals "js:" in hx-vals as an inline object literal, not a bare
    # function call; the old js:getAddToCartVals() form silently aborts the request.
    assert 'hx-vals=\'js:{qty: getQuantity(), attributes: getAttributesString()}\'' in resp.text
    assert "function getQuantity()" in resp.text
    assert "function getAttributesString()" in resp.text
    assert "js:getAddToCartVals()" not in resp.text
    # In-flight + success feedback (spinner/checkmark overlay) on both detail buttons.
    # The old htmx-request-based classes are gone so a lingering request class
    # can't keep the spinner visible after the flash.
    assert resp.text.count('class="btn-spinner') == 2
    assert resp.text.count('class="btn-checkmark') == 2
    # CSS is now inlined into base.html, so only assert on markup class usage
    # (the compiled stylesheet legitimately contains .htmx-indicator rules).
    assert 'class="htmx-indicator' not in resp.text
    assert "hx-disabled-elt" not in resp.text


@pytest.mark.asyncio
async def test_listing_add_buttons_keep_original_icon_only_markup():
    for path in ("/", "/shop"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert 'hx-post="/cart/add/' in resp.text
        assert 'class="btn-spinner' not in resp.text
        assert 'class="btn-checkmark' not in resp.text
        assert 'class="btn-content' not in resp.text

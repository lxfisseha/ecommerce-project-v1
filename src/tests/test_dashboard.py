import pytest
import pytest_asyncio
from src.features.orders.models import Order
from src.features.auth.models import Seller
from src.utils.datetime import utc_now
from src.utils.crypto import encrypt_phone, hash_phone
from src.tests.conftest import client, maker, get_csrf_context, current_seller_override


@pytest_asyncio.fixture
async def seeded_order():
    async with maker() as session:
        order = Order(
            order_id="ET-STATUS-0001", seller_id=1, buyer_name="Buyer",
            buyer_phone="ENC_P", buyer_phone_hash="HASH_P",
            delivery_address="ENC_A", delivery_address_hash="HASH_A",
            product_id=1, product_name="Product", product_price=100,
            quantity=1, subtotal=100, total_amount=250, status="pending",
            created_at=utc_now(), status_updated_at=utc_now(),
        )
        session.add(order)
        await session.commit()
        return order.id


@pytest.mark.asyncio
async def test_update_order_status_invalid_enum(seeded_order, current_seller_override):
    """Fix 42: dashboard route rejects invalid status values."""
    token, csrf_cookie = get_csrf_context(client)
    response = client.post(
        f"/dashboard/orders/{seeded_order}/status",
        data={"new_status": "invalid_status"},
        cookies={"csrftoken": csrf_cookie},
        headers={"X-CSRF-Token": token}
    )
    assert response.status_code == 400

import pytest
import pytest_asyncio
from src.features.orders.models import Order, OrderStatusLog
from src.features.orders.services import OrderService
from sqlmodel import select
from src.features.products.models import Product
from decimal import Decimal
from src.tests.conftest import maker


@pytest.mark.asyncio
async def test_order_audit_logging_flow():
    """
    Verify that creating an order and updating its status correctly creates audit logs.
    """
    async with maker() as db_session:
        # 1. Setup a product (seller id=1 already seeded by conftest)
        product = Product(
            id=1, seller_id=1, name="TP", description="TD", price=Decimal("100.00"), in_stock=True
        )
        db_session.add(product)
        await db_session.commit()

        # Create order
        order = await OrderService.create_order(
            db_session, product, "Buyer", "0911111111", "Addr", 1, store_prefix="TEST"
        )

        # 2. Verify initial log (created during create_order)
        logs_stmt = select(OrderStatusLog).where(OrderStatusLog.order_id == order.id).order_by(OrderStatusLog.changed_at)
        logs = (await db_session.execute(logs_stmt)).scalars().all()

        assert len(logs) == 1
        assert logs[0].new_status == "pending"
        assert logs[0].changed_by == "system"
        assert logs[0].context == "Order created"

        # 3. Update status and verify log creation
        new_context = "Buyer confirmed shipping"
        await OrderService.update_order_status(db_session, order.id, "shipped", changed_by="seller", context=new_context)

        # 4. Verify logs after update
        logs = (await db_session.execute(logs_stmt)).scalars().all()
        assert len(logs) == 2
        assert logs[1].old_status == "pending"
        assert logs[1].new_status == "shipped"
        assert logs[1].changed_by == "seller"
        assert logs[1].context == new_context

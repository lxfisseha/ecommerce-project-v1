from src.utils.datetime import utc_now
from typing import Optional, List
from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.features.orders.models import Order, OrderStatusLog
from src.features.auth.models import Seller
from src.features.products.models import Product
from src.utils.crypto import encrypt_data
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class NotificationService:
    @staticmethod
    async def send_order_confirmation(order: Order, seller: Seller):
        """
        FR15: Dispatch receipt copy via SMS or Telegram.
        Mock implementation for v1.
        """
        logger.info(f"NOTIFICATION: Sending order confirmation for {order.order_id} to {order.buyer_phone}")
        # In a real app, this would call an external API like AfroMessage or a Telegram Bot
        pass

class OrderService:
    @staticmethod
    async def generate_order_id(db: AsyncSession, seller_id: int) -> str:
        """
        Generates a unique order ID: ET-[store prefix]-[YYYYMMDD]-[0001]
        """
        # Get seller for prefix
        seller = await db.get(Seller, seller_id)
        if not seller:
            raise ValueError("Seller not found")
        
        prefix = seller.store_prefix.upper()
        today_str = utc_now().strftime("%Y%m%d")
        
        # Count orders for this seller today to get the next sequence
        statement = select(func.count(Order.id)).where(
            Order.seller_id == seller_id,
            Order.order_id.like(f"ET-{prefix}-{today_str}-%")
        )
        result = await db.execute(statement)
        count = result.scalar() or 0
        sequence = str(count + 1).zfill(4)
        
        return f"ET-{prefix}-{today_str}-{sequence}"

    @staticmethod
    async def create_order(
        db: AsyncSession,
        product: Product,
        buyer_name: str,
        buyer_phone: str,
        delivery_address: str,
        quantity: int,
        attributes_selected: Optional[str] = None
    ) -> Order:
        """
        Creates a new order and logs the initial status.
        FR10: Full Name, Phone Number, Delivery Address.
        5.2: AES-256 encryption for phone and address.
        """
        order_id = await OrderService.generate_order_id(db, product.seller_id)
        
        # Normalize phone number to 9-digit format
        from src.utils.phone import normalize_phone
        buyer_phone = normalize_phone(buyer_phone)
        
        # Calculate subtotal and total (v1: 150 ETB fixed delivery fee)
        delivery_fee = Decimal("150.0")
        subtotal = product.price * quantity
        total_amount = subtotal + delivery_fee
        
        # Encrypt sensitive data (AES-256 via Fernet)
        encrypted_phone = encrypt_data(buyer_phone)
        encrypted_address = encrypt_data(delivery_address)
        
        # Create hashes for lookup
        from src.utils.crypto import hash_data
        phone_h = hash_data(buyer_phone)
        address_h = hash_data(delivery_address)
        
        order = Order(
            order_id=order_id,
            seller_id=product.seller_id,
            buyer_name=buyer_name,
            buyer_phone=encrypted_phone,
            buyer_phone_hash=phone_h,
            delivery_address=encrypted_address,
            delivery_address_hash=address_h,
            product_id=product.id,
            product_name=product.name,
            product_price=product.price,
            quantity=quantity,
            attributes_selected=attributes_selected,
            subtotal=subtotal,
            total_amount=total_amount,
            status="pending"
        )
        
        db.add(order)
        await db.flush() # Get order.id
        
        # Log status
        log = OrderStatusLog(
            order_id=order.id,
            new_status="pending",
            changed_by="system"
        )
        db.add(log)
        
        await db.commit()
        await db.refresh(order)
        
        # Trigger Notification
        seller = await db.get(Seller, product.seller_id)
        await NotificationService.send_order_confirmation(order, seller)
        
        return order

    @staticmethod
    async def update_order_status(
        db: AsyncSession,
        order_id: int,
        new_status: str,
        changed_by: str = "seller"
    ) -> Order:
        """
        FR17/FR18: State machine workflow and terminal state locks.
        """
        order = await db.get(Order, order_id)
        if not order:
            raise ValueError("Order not found")
        
        # FR18: Terminal state locks
        if order.status in ["completed", "cancelled"]:
            raise ValueError(f"Cannot update order in terminal state '{order.status}'")
        
        # FR17: Workflow validation (Optional: v1 might allow any forward move)
        # But PRD says pending -> shipped -> completed
        valid_transitions = {
            "pending": ["shipped", "cancelled"],
            "shipped": ["completed", "cancelled"],
        }
        
        if new_status not in valid_transitions.get(order.status, []):
            raise ValueError(f"Invalid transition from {order.status} to {new_status}")
            
        old_status = order.status
        order.status = new_status
        order.status_updated_at = utc_now()
        
        # Log transition
        log = OrderStatusLog(
            order_id=order.id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by
        )
        db.add(log)
        db.add(order)
        await db.commit()
        await db.refresh(order)
        return order

    @staticmethod
    async def get_order_by_reference(db: AsyncSession, order_reference: str) -> Optional[Order]:
        """
        Retrieves an order by its public ET-... reference.
        """
        statement = select(Order).where(Order.order_id == order_reference)
        result = await db.execute(statement)
        return result.scalar_one_or_none()

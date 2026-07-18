import asyncio

from src.utils.datetime import utc_now
from typing import Dict, Optional, List
from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.features.orders.models import Order, OrderStatusLog
from src.features.auth.models import Seller
from src.features.products.models import Product
from src.utils.crypto import encrypt_data, hash_data
from src.utils.phone import normalize_phone
from src.constants import DELIVERY_FEE
from decimal import Decimal
import logging

from src.utils.sms import AfroMessageService


def parse_selected_attributes(attributes_str: Optional[str]) -> Dict[str, str]:
    selected = {}
    if not attributes_str:
        return selected

    for part in attributes_str.split(","):
        if ":" in part:
            key, value = part.split(":", 1)
            selected[key.strip()] = value.strip()

    return selected


def calculate_attribute_extra_price(
    product: Product, selected_attrs: Dict[str, str]
) -> Decimal:
    extra = Decimal("0.0")
    if not selected_attrs:
        return extra

    for attr in product.attributes:
        if selected_attrs.get(attr.attribute_type) == attr.attribute_value:
            extra += attr.extra_price

    return extra


logger = logging.getLogger(__name__)


class NotificationService:
    @classmethod
    async def send_order_confirmation(cls, order, seller, raw_buyer_phone: str) -> None:
        """
        Processes multi-channel order confirmations. Dispatches external SMS
        notifications to the buyer and seller asynchronously in the background.
        """

        # 1. Safely construct the item description summary string
        item_summary = f"{order.quantity}x {order.product_name}"
        if order.attributes_selected:
            item_summary += f" ({order.attributes_selected})"

        # 2. Extract seller's phone number securely
        # It handles both dictionary payloads and standard ORM attributes
        seller_phone = (
            getattr(seller, "business_contact_number", "")
            if not isinstance(seller, dict)
            else seller.get("business_contact_number", "")
        )

        if not seller_phone:
            logger.warning(
                f"Skipping SMS notifications for Order #{order.order_id}. "
                f"Reason: Seller phone number is missing or empty."
            )
            return

        # 3. Schedule the SMS execution as a background task
        # Using asyncio.create_task avoids waiting for the external HTTP call to finish,
        # protecting your API route from hanging or timing out if AfroMessage is slow.
        try:
            asyncio.create_task(
                AfroMessageService.send_order_notifications_sms(
                    buyer_phone=raw_buyer_phone,
                    seller_phone=str(seller_phone),
                    order_id=str(order.order_id),
                    total_amount=float(order.total_amount),
                    item_summary=item_summary,
                )
            )
            logger.info(
                f"Successfully queued background SMS notifications for Order #{order.order_id}"
            )

        except Exception as e:
            # Shielding: We catch all exceptions here so a failing SMS initialization
            # never crashes the database transaction or the user's checkout redirection.
            logger.error(
                f"Failed to initialize background AfroMessage tasks for Order #{order.order_id}: {str(e)}"
            )


class OrderService:
    @staticmethod
    async def generate_order_id(db: AsyncSession, store_prefix: str) -> str:
        """
        Generates a unique order ID: ET-[store prefix]-[YYYYMMDD]-[0001]
        Uses the seller's store prefix directly instead of fetching the Seller row.
        """
        prefix = store_prefix.upper()
        today_str = utc_now().strftime("%Y%m%d")

        # Count orders today to get the next sequence
        statement = select(func.count(Order.id)).where(
            Order.order_id.like(f"ET-{prefix}-{today_str}-%"),
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
        attributes_selected: Optional[str] = None,
        store_prefix: Optional[str] = None,
    ) -> Order:
        """
        Creates a new order and logs the initial status.
        FR10: Full Name, Phone Number, Delivery Address.
        5.2: AES-256 encryption for phone and address.
        """
        if not store_prefix:
            raise ValueError("store_prefix is required to generate order ID")

        if quantity < 1:
            raise ValueError("Quantity must be at least 1.")
        if quantity > 100:
            raise ValueError("Quantity cannot exceed 100 per order.")

        order_id = await OrderService.generate_order_id(db, store_prefix)

        # Ensure product relationships are loaded for attribute matching
        if "attributes" not in product.__dict__:
            product_result = await db.execute(
                select(Product)
                .where(Product.id == product.id)
                .options(selectinload(Product.attributes))
            )
            product = product_result.scalar_one_or_none()
            if not product:
                raise ValueError("Product not found")

        # Normalize phone number to 9-digit format
        buyer_phone = normalize_phone(buyer_phone)

        # Calculate subtotal and total (v1: 150 ETB fixed delivery fee)
        delivery_fee = DELIVERY_FEE
        selected_attrs = parse_selected_attributes(attributes_selected)
        extra_price = calculate_attribute_extra_price(product, selected_attrs)
        subtotal = (product.price + extra_price) * quantity
        total_amount = subtotal + delivery_fee

        # Encrypt sensitive data (AES-256 via Fernet)
        encrypted_phone = encrypt_data(buyer_phone)
        encrypted_address = encrypt_data(delivery_address)

        # Create hashes for lookup
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
            status="pending",
        )

        db.add(order)
        await db.flush()  # Get order.id

        # Log status
        log = OrderStatusLog(
            order_id=order.id,
            new_status="pending",
            changed_by="system",
            context="Order created",
        )
        db.add(log)

        await db.commit()
        await db.refresh(order)

        # Trigger Notification
        seller = await db.get(Seller, product.seller_id)
        await NotificationService.send_order_confirmation(order, seller, buyer_phone)

        return order

    @staticmethod
    async def update_order_status(
        db: AsyncSession,
        order_id: int,
        new_status: str,
        changed_by: str = "seller",
        context: Optional[str] = None,
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

        # FR17: Workflow validation
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
            changed_by=changed_by,
            context=context,
        )
        db.add(log)
        db.add(order)
        await db.commit()
        await db.refresh(order)
        return order

    @staticmethod
    async def get_order_by_reference(
        db: AsyncSession, order_reference: str
    ) -> Optional[Order]:
        """
        Retrieves an order by its public ET-... reference.
        """
        statement = select(Order).where(Order.order_id == order_reference)
        result = await db.execute(statement)
        return result.scalar_one_or_none()

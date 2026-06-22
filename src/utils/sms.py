import asyncio
import logging
import httpx
from src.config import settings

logger = logging.getLogger(__name__)


class AfroMessageService:
    """
    Service to handle sending SMS notifications using the AfroMessage API provider.
    Sourced from the service provider's code example.
    """

    BASE_URL = "https://api.afromessage.com/api/send"

    @classmethod
    def _format_phone(cls, phone_number: str) -> str:
        """Normalizes Ethiopian phone numbers to the format expected by AfroMessage."""
        if phone_number.startswith("0"):
            return "251" + phone_number[1:]
        if phone_number.startswith("9") or phone_number.startswith("7"):
            return "251" + phone_number
        return phone_number

    @classmethod
    async def _dispatch_sms(
        cls,
        client: httpx.AsyncClient,
        api_key: str,
        to_phone: str,
        message: str,
        recipient_label: str,
    ) -> bool:
        """Internal low-level dispatcher to send an SMS payload via a shared client session."""
        sender = getattr(settings, "AFROMESSAGES_SENDER", "AleMart")
        from_id = getattr(settings, "AFROMESSAGES_FROM", "")
        callback = getattr(settings, "AFROMESSAGES_CALLBACK", "")

        headers = {"Authorization": f"Bearer {api_key}"}
        params = {
            "from": from_id,
            "sender": sender,
            "to": to_phone,
            "message": message,
            "callback": callback,
        }

        logger.info(
            f"Attempting to send {recipient_label} SMS via AfroMessage to {to_phone}"
        )

        try:
            print(
                f"\n\n\nAttempting to send {recipient_label} SMS via AfroMessage to {to_phone} with message: {message}"
            )
            response = await client.get(
                cls.BASE_URL, headers=headers, params=params, timeout=10.0
            )

            print(
                f"\n\n\nAfroMessage API response for {recipient_label} to {to_phone}: "
                f"Status {response.status_code}, Content: {response.text}"
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("acknowledge") == "success":
                    logger.info(
                        f"SMS successfully sent to {recipient_label} ({to_phone})."
                    )
                    return True

                logger.error(f"AfroMessage API failure for {recipient_label}: {data}")
                return False

            logger.error(
                f"AfroMessage HTTP error for {recipient_label}. "
                f"Status: {response.status_code}, Content: {response.text}"
            )
            return False

        except Exception as e:
            logger.error(
                f"Exception occurred while sending {recipient_label} SMS to {to_phone}: {str(e)}"
            )
            return False

    @classmethod
    async def send_otp_sms(cls, phone_number: str, otp_code: str) -> bool:
        """
        Sends an OTP verification code to a specified Ethiopian phone number.
        Returns True if successful, False otherwise.
        """
        api_key = settings.AFROMESSAGES_API_KEY
        message = (
            f"Your AleMart login verification code is: {otp_code}. Valid for 5 minutes."
        )

        if not api_key:
            logger.warning(
                f"[SMS MOCK] AFROMESSAGES_API_KEY not configured. "
                f"Would send OTP {otp_code} to {phone_number}"
            )
            return True

        formatted_phone = cls._format_phone(phone_number)

        async with httpx.AsyncClient() as client:
            return await cls._dispatch_sms(
                client, api_key, formatted_phone, message, "OTP"
            )

    @classmethod
    async def send_order_notifications_sms(
        cls,
        buyer_phone: str,
        seller_phone: str,
        order_id: str,
        total_amount: float,
        item_summary: str,
    ) -> dict[str, bool]:
        """
        Sends an order confirmation SMS to the buyer and an order summary SMS to the seller.
        Returns a dictionary indicating the success status of both operations.
        """
        api_key = settings.AFROMESSAGES_API_KEY

        buyer_message = f"Thank you for your order at AleMart! Your Order #{order_id} has been placed successfully. Total: {total_amount:.2f}."
        seller_message = f"AleMart Alert: You have a new order #{order_id}. Items: {item_summary}. Total payout: {total_amount:.2f}."

        if not api_key:
            logger.warning(
                f"[SMS MOCK] AFROMESSAGES_API_KEY not configured.\n"
                f"Would send Buyer SMS to {buyer_phone}: {buyer_message}\n"
                f"Would send Seller SMS to {seller_phone}: {seller_message}"
            )
            return {"buyer_success": True, "seller_success": True}

        formatted_buyer_phone = cls._format_phone(buyer_phone)
        formatted_seller_phone = cls._format_phone(seller_phone)

        async with httpx.AsyncClient() as client:
            buyer_task = cls._dispatch_sms(
                client, api_key, formatted_buyer_phone, buyer_message, "Buyer"
            )
            seller_task = cls._dispatch_sms(
                client, api_key, formatted_seller_phone, seller_message, "Seller"
            )

            buyer_res, seller_res = await asyncio.gather(buyer_task, seller_task)

        return {"buyer_success": buyer_res, "seller_success": seller_res}

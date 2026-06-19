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
    async def send_otp_sms(cls, phone_number: str, otp_code: str) -> bool:
        """
        Sends an OTP verification code to a specified Ethiopian phone number.
        Returns True if successful, False otherwise.
        """
        api_key = settings.AFROMESSAGES_API_KEY
        if not api_key:
            logger.warning(
                f"[SMS MOCK] AFROMESSAGES_API_KEY not configured. "
                f"Would send OTP {otp_code} to {phone_number}"
            )
            return True

        # Ensure the phone number format starts with the expected country prefix or as normalized.
        # AfroMessage expects phone numbers in a standard format (usually starting with +251 or 251 or as normalized).
        # Ethiopian numbers are stored/input as 09... or 07...
        # If the number starts with '0', we can convert it to '251' or keep it based on local provider requirements.
        # Let's format it cleanly to 251... or keep as input if the provider accepts it.
        # Let's ensure standard format by checking if it starts with 0:
        formatted_phone = phone_number
        if phone_number.startswith("0"):
            formatted_phone = "251" + phone_number[1:]

        message = (
            f"Your AleMart login verification code is: {otp_code}. Valid for 5 minutes."
        )

        # Configure additional optional fields with safe defaults or settings
        sender = getattr(settings, "AFROMESSAGES_SENDER", "AleMart")
        from_id = getattr(settings, "AFROMESSAGES_FROM", "")
        callback = getattr(settings, "AFROMESSAGES_CALLBACK", "")

        headers = {"Authorization": f"Bearer {api_key}"}

        params = {
            "from": from_id,
            "sender": sender,
            "to": formatted_phone,
            "message": message,
            "callback": callback,
        }

        print(
            f"\n\n\nAttempting to send OTP SMS via AfroMessage to {formatted_phone} with message: {message}\n\n\n"
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    cls.BASE_URL, headers=headers, params=params, timeout=10.0
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("acknowledge") == "success":
                        logger.info(
                            f"SMS successfully sent to {formatted_phone} via AfroMessage."
                        )
                        return True
                    else:
                        logger.error(f"AfroMessage API failure response: {data}")
                        return False
                else:
                    logger.error(
                        f"AfroMessage HTTP error. Status: {response.status_code}, Content: {response.text}"
                    )
                    return False
        except Exception as e:
            logger.error(
                f"Exception occurred while trying to send SMS via AfroMessage: {str(e)}"
            )
            return False

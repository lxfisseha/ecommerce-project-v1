from typing import Optional
import re
from datetime import datetime, timedelta
import secrets
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Seller, OtpCode
from src.utils.crypto import encrypt_phone, hash_phone
from src.utils.datetime import utc_now

from src.utils.phone import validate_ethiopian_phone, normalize_phone


class AuthService:
    @staticmethod
    async def get_seller_by_phone(db: AsyncSession, phone: str) -> Optional[Seller]:
        # Normalize input to ensure consistency
        phone = normalize_phone(phone)
        # Use deterministic hash for lookup
        phone_h = hash_phone(phone)
        statement = select(Seller).where(Seller.phone_hash == phone_h)
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def generate_otp(db: AsyncSession, phone: str) -> tuple[str, bool]:
        # Normalize input
        phone = normalize_phone(phone)
        # Generate a 6-digit code
        code = "".join([str(secrets.randbelow(10)) for _ in range(6)])

        # Set expiry to 5 minutes from now
        expires_at = utc_now() + timedelta(minutes=5)

        otp = OtpCode(
            phone=encrypt_phone(phone),  # Encrypt phone for retrieval
            phone_hash=hash_phone(phone),  # Store hash for lookup
            code=code,
            expires_at=expires_at,
        )

        db.add(otp)
        await db.commit()

        # Trigger sending the SMS code via AfroMessage
        from src.utils.sms import AfroMessageService

        sms_success = await AfroMessageService.send_otp_sms(phone, code)

        return code, sms_success

    @staticmethod
    async def verify_otp(db: AsyncSession, phone: str, code: str) -> dict:
        # Normalize input
        phone = normalize_phone(phone)
        phone_h = hash_phone(phone)
        now = utc_now()
        statement = (
            select(OtpCode)
            .where(OtpCode.phone_hash == phone_h)
            .where(OtpCode.used == False)
            .where(OtpCode.expires_at > now)
            .order_by(OtpCode.created_at.desc())
        )
        result = await db.execute(statement)
        otp = result.first()
        if otp:
            otp = otp[0]  # result.first() returns a row, so extract the OtpCode object

        if not otp:
            return {
                "success": False,
                "message": "Verification code expired or not found.",
            }

        # Check attempts
        if otp.attempts >= 3:
            return {
                "success": False,
                "message": "Too many attempts. Please request a new code.",
            }

        # Validate code
        if otp.code != code:
            otp.attempts += 1
            db.add(otp)
            await db.commit()
            return {
                "success": False,
                "message": f"Invalid code. {3 - otp.attempts} attempts remaining.",
            }

        # Success
        otp.used = True
        db.add(otp)
        await db.commit()
        return {"success": True}

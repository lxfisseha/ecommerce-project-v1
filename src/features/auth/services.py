from typing import Optional
import re
import hmac as hmac_mod
from datetime import datetime, timedelta
import secrets
from sqlmodel import select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Seller, OtpCode
from src.utils.crypto import encrypt_phone, hash_phone, legacy_hash_phone
from src.utils.datetime import utc_now

from src.utils.phone import validate_ethiopian_phone, normalize_phone


class AuthService:
    @staticmethod
    async def get_seller_by_phone(db: AsyncSession, phone: str) -> Optional[Seller]:
        phone = normalize_phone(phone)
        phone_h = hash_phone(phone)
        statement = select(Seller).where(Seller.phone_hash == phone_h)
        result = await db.execute(statement)
        seller = result.scalar_one_or_none()
        if seller:
            return seller
        phone_h = legacy_hash_phone(phone)
        statement = select(Seller).where(Seller.phone_hash == phone_h)
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def generate_otp(db: AsyncSession, phone: str) -> tuple[str, bool]:
        phone = normalize_phone(phone)
        code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
        print(f"[DEV] OTP for {phone}: {code}")

        expires_at = utc_now() + timedelta(minutes=5)

        otp = OtpCode(
            phone=encrypt_phone(phone),
            phone_hash=hash_phone(phone),
            code=code,
            expires_at=expires_at,
        )

        db.add(otp)
        await db.flush()

        # Invalidate all previous unused OTPs for this phone
        phone_h = hash_phone(phone)
        prev_stmt = select(OtpCode).where(
            OtpCode.phone_hash == phone_h,
            OtpCode.used == False,
            OtpCode.id != otp.id,
        )
        prev_otps = (await db.execute(prev_stmt)).scalars().all()
        for old in prev_otps:
            old.used = True
            db.add(old)

        await db.commit()

        from src.utils.sms import AfroMessageService
        sms_success = await AfroMessageService.send_otp_sms(phone, code)

        return code, sms_success

    @staticmethod
    async def verify_otp(db: AsyncSession, phone: str, code: str) -> dict:
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
            otp = otp[0]

        if not otp:
            phone_h = legacy_hash_phone(phone)
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
                otp = otp[0]

        if not otp:
            return {
                "success": False,
                "message": "Verification code expired or not found.",
            }

        if otp.attempts >= 3:
            return {
                "success": False,
                "message": "Too many attempts. Please request a new code.",
            }

        # Timing-safe comparison + atomic attempt increment
        if not hmac_mod.compare_digest(otp.code, code):
            await db.execute(
                update(OtpCode)
                .where(OtpCode.id == otp.id)
                .values(attempts=OtpCode.attempts + 1)
            )
            await db.commit()
            refreshed = await db.get(OtpCode, otp.id)
            remaining = max(0, 3 - (refreshed.attempts if refreshed else 0))
            return {
                "success": False,
                "message": f"Invalid code. {remaining} attempts remaining.",
            }

        # Success
        otp.used = True
        db.add(otp)
        await db.commit()
        return {"success": True}

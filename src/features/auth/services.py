from typing import Optional
import re
import asyncio
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

# Keep strong references to background tasks so they aren't garbage-collected
# mid-flight (asyncio drops tasks with no references).
_background_tasks: set = set()


def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


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
    async def generate_otp(db: AsyncSession, phone: str) -> str:
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

        # Invalidate all previous unused OTPs for this phone in a single UPDATE
        phone_h = hash_phone(phone)
        await db.execute(
            update(OtpCode)
            .where(
                OtpCode.phone_hash == phone_h,
                OtpCode.used == False,
                OtpCode.id != otp.id,
            )
            .values(used=True)
        )

        await db.commit()

        # Send the SMS in the background so the login request never waits on
        # the external HTTP call.
        from src.utils.sms import AfroMessageService
        _spawn_background(AfroMessageService.send_otp_sms(phone, code))

        return code

    @staticmethod
    async def _get_unused_otp(db: AsyncSession, phone_hash: str, now) -> Optional[OtpCode]:
        statement = (
            select(OtpCode)
            .where(OtpCode.phone_hash == phone_hash)
            .where(OtpCode.used == False)
            .where(OtpCode.expires_at > now)
            .order_by(OtpCode.created_at.desc())
        )
        result = await db.execute(statement)
        row = result.first()
        return row[0] if row else None

    @staticmethod
    async def _get_seller_by_hash(db: AsyncSession, phone_hash: str) -> Optional[Seller]:
        statement = select(Seller).where(Seller.phone_hash == phone_hash)
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def verify_otp(db: AsyncSession, phone: str, code: str) -> dict:
        phone = normalize_phone(phone)
        phone_h = hash_phone(phone)
        legacy_phone_h = legacy_hash_phone(phone)
        now = utc_now()

        otp = await AuthService._get_unused_otp(db, phone_h, now)
        matched_hash = phone_h
        if not otp:
            otp = await AuthService._get_unused_otp(db, legacy_phone_h, now)
            matched_hash = legacy_phone_h

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

        # Timing-safe comparison + atomic attempt increment (single UPDATE ... RETURNING)
        if not hmac_mod.compare_digest(otp.code, code):
            result = await db.execute(
                update(OtpCode)
                .where(OtpCode.id == otp.id)
                .values(attempts=OtpCode.attempts + 1)
                .returning(OtpCode.attempts)
            )
            await db.commit()
            attempts = result.scalar() or 0
            remaining = max(0, 3 - attempts)
            return {
                "success": False,
                "message": f"Invalid code. {remaining} attempts remaining.",
            }

        # Success
        otp.used = True
        db.add(otp)
        await db.commit()

        seller = await AuthService._get_seller_by_hash(db, matched_hash)
        return {"success": True, "seller": seller}

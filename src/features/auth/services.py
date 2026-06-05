from typing import Optional
import re
from datetime import datetime, timedelta
import secrets
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Seller, OtpCode
from src.utils.crypto import encrypt_phone, decrypt_phone

def validate_ethiopian_phone(phone: str) -> bool:
    """
    Validates Ethiopian phone numbers (without leading 0).
    Must start with 9 or 7 and be exactly 9 digits.
    """
    pattern = r"^[97]\d{8}$"
    return bool(re.match(pattern, phone))

class AuthService:
    @staticmethod
    async def get_seller_by_phone(db: AsyncSession, phone: str) -> Optional[Seller]:
        # Encrypt the input phone to match the stored encrypted value
        encrypted_phone = encrypt_phone(phone)
        print(f"DEBUG: Searching for phone: {phone}, Encrypted: {encrypted_phone}")
        statement = select(Seller).where(Seller.phone == encrypted_phone)
        result = await db.execute(statement)
        seller = result.scalar_one_or_none()
        print(f"DEBUG: Seller found: {seller is not None}")
        return seller

    @staticmethod
    async def generate_otp(db: AsyncSession, phone: str) -> str:
        # Generate a 6-digit code
        code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
        
        # Set expiry to 5 minutes from now
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        
        otp = OtpCode(
            phone=encrypt_phone(phone), # Encrypt phone in OTP storage
            code=code,
            expires_at=expires_at
        )
        
        print("here is the otp code", code)

        db.add(otp)
        await db.commit()
        
        return code

    @staticmethod
    async def verify_otp(db: AsyncSession, phone: str, code: str) -> dict:
        encrypted_phone = encrypt_phone(phone)
        statement = (
            select(OtpCode)
            .where(OtpCode.phone == encrypted_phone)
            .where(OtpCode.used == False)
            .where(OtpCode.expires_at > datetime.utcnow())
            .order_by(OtpCode.created_at.desc())
        )
        result = await db.execute(statement)
        otp = result.first()
        if otp:
            otp = otp[0] # result.first() returns a row, so extract the OtpCode object
        
        if not otp:
            return {"success": False, "message": "Verification code expired or not found."}

        # Check attempts
        if otp.attempts >= 3:
            return {"success": False, "message": "Too many attempts. Please request a new code."}

        # Validate code
        if otp.code != code:
            otp.attempts += 1
            db.add(otp)
            await db.commit()
            return {"success": False, "message": f"Invalid code. {3 - otp.attempts} attempts remaining."}

        # Success
        otp.used = True
        db.add(otp)
        await db.commit()
        return {"success": True}

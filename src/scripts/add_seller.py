import asyncio
from src.database import async_session_maker
from src.features.auth.models import Seller
from src.utils.crypto import encrypt_phone
from sqlmodel import select

async def add_sample_seller():
    async with async_session_maker() as session:
        # Phone to add
        phone_raw = "912345678"
        encrypted_phone = encrypt_phone(phone_raw)
        
        # Check if already exists
        statement = select(Seller).where(Seller.phone == encrypted_phone)
        result = await session.execute(statement)
        if result.scalar_one_or_none():
            print("Seller with this phone number already exists.")
            return

        seller = Seller(
            first_name="Fanuel",
            last_name="Alemu",
            store_name="AleMart Demo Store",
            store_prefix="DEMO",
            phone=encrypted_phone
        )
        session.add(seller)
        await session.commit()
        print(f"Sample seller 'AleMart Demo Store' added successfully with phone {phone_raw}.")

if __name__ == "__main__":
    asyncio.run(add_sample_seller())

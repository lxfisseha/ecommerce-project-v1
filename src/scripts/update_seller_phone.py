import asyncio
from src.database import async_session_maker
from src.features.auth.models import Seller
from src.utils.crypto import encrypt_phone, hash_phone
from src.utils.phone import normalize_phone
from sqlmodel import select

async def update_seller_phone():
    async with async_session_maker() as session:
        # Find the seller
        statement = select(Seller)
        result = await session.execute(statement)
        sellers = result.scalars().all()
        
        if not sellers:
            print("No sellers found in the database to update.")
            return

        target_phone = "968954922"
        phone_normalized = normalize_phone(target_phone)
        phone_encrypted = encrypt_phone(phone_normalized)
        phone_hash = hash_phone(phone_normalized)

        for seller in sellers:
            print(f"Updating seller '{seller.store_name}' (ID: {seller.id}) phone number to {phone_normalized}...")
            seller.phone = phone_encrypted
            seller.phone_hash = phone_hash
            session.add(seller)
            
        await session.commit()
        print("All sellers successfully updated.")

if __name__ == "__main__":
    asyncio.run(update_seller_phone())

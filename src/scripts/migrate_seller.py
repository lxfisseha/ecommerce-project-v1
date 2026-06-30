import asyncio
from src.database import async_session_maker
from src.features.auth.models import Seller
from src.utils.crypto import encrypt_phone, hash_phone
from src.utils.phone import normalize_phone
from sqlmodel import select

TARGET_PHONE = "968954922"

async def migrate_sellers():
    phone_normalized = normalize_phone(TARGET_PHONE)
    phone_encrypted = encrypt_phone(phone_normalized)
    phone_hash = hash_phone(phone_normalized)

    async with async_session_maker() as session:
        statement = select(Seller)
        result = await session.execute(statement)
        sellers = result.scalars().all()

        if not sellers:
            print("No sellers found in the database.")
            return

        for seller in sellers:
            print(f"Processing seller '{seller.store_name}' (ID: {seller.id})...")

            new_store_name = f"{seller.store_name} (local)"
            new_store_prefix = f"{seller.store_prefix}_L"

            existing = await session.execute(
                select(Seller).where(Seller.store_name == new_store_name)
            )
            if existing.scalar_one_or_none():
                print(f"  Skipped — '{new_store_name}' already exists.")
                continue

            new_seller = Seller(
                first_name=seller.first_name,
                last_name=seller.last_name,
                store_name=new_store_name,
                store_prefix=new_store_prefix,
                phone=phone_encrypted,
                phone_hash=phone_hash,
                business_email=seller.business_email,
                business_address=seller.business_address,
                telegram_username=seller.telegram_username,
                business_contact_number=seller.business_contact_number,
                featured_image=seller.featured_image,
            )
            session.add(new_seller)
            print(f"  Created new seller '{new_store_name}' (prefix: {new_store_prefix})")

        await session.commit()
        print("Migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate_sellers())

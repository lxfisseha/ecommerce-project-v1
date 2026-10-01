import asyncio
from src.database import async_session_maker
from src.features.auth.models import Seller
from src.utils.crypto import encrypt_phone
from sqlmodel import select

SAMPLE_FEATURED_IMAGE_URL = (
    "https://images.unsplash.com/photo-1547949003-9792a18a2601"
    "?auto=format&fit=crop&q=80&w=1600"
)


def _store_featured_image() -> str | None:
    """
    Put the sample hero image into local storage and return its object key.

    featured_image is an object key, not a URL, so a remote URL would render
    as a broken src. Returns None if the download fails, leaving the seller
    without a hero image rather than a broken one.
    """
    import logging
    import urllib.request

    logger = logging.getLogger(__name__)
    try:
        request = urllib.request.Request(
            SAMPLE_FEATURED_IMAGE_URL, headers={"User-Agent": "xcollections-seed/1.0"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
    except Exception as exc:
        logger.warning("Could not fetch sample featured image: %s", exc)
        return None

    if not data:
        return None

    from src.utils.storage import LocalStorage

    return LocalStorage().save(data, "featured.jpg", folder="sellers/demo/featured")

async def add_sample_seller():
    async with async_session_maker() as session:
        # Phone to add
        phone_raw = "912345678"
        from src.utils.phone import normalize_phone, validate_ethiopian_phone
        from src.utils.crypto import hash_phone, encrypt_phone
        
        # Normalize and validate
        phone_normalized = normalize_phone(phone_raw)
        if not validate_ethiopian_phone(phone_normalized):
            print(f"Invalid phone number: {phone_raw}")
            return
            
        phone_h = hash_phone(phone_normalized)
        
        featured_image = _store_featured_image()

        # Check if already exists by store_name
        statement = select(Seller).where(Seller.store_name == "XCollections Demo Store")
        result = await session.execute(statement)
        seller = result.scalar_one_or_none()

        if seller:
            print(f"Updating existing seller '{seller.store_name}'...")
            seller.phone = encrypt_phone(phone_normalized)
            seller.phone_hash = phone_h
            if featured_image:
                seller.featured_image = featured_image
            seller.business_contact_number = phone_normalized
            session.add(seller)
        else:
            print("Creating new sample seller...")
            seller = Seller(
                first_name="Fanuel",
                last_name="Alemu",
                store_name="XCollections Demo Store",
                store_prefix="DEMO",
                phone=encrypt_phone(phone_normalized),
                phone_hash=phone_h,
                featured_image=featured_image or "",
                business_contact_number=phone_normalized
            )
            session.add(seller)
        
        await session.commit()
        print(f"Sample seller 'XCollections Demo Store' handled successfully with phone {phone_normalized}.")

if __name__ == "__main__":
    asyncio.run(add_sample_seller())

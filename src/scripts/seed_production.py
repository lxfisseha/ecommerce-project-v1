import asyncio
import argparse
from src.database import async_session_maker
from src.features.auth.models import Seller
from src.utils.crypto import encrypt_phone, hash_phone
from src.utils.phone import normalize_phone, validate_ethiopian_phone
from sqlmodel import select


SAMPLE_FEATURED_IMAGE_URL = (
    "https://images.unsplash.com/photo-1547949003-9792a18a2601"
    "?auto=format&fit=crop&q=80&w=1600"
)


def _store_featured_image() -> str:
    """
    Put the sample hero image into local storage and return its object key.

    featured_image holds an object key, not a URL, so storing the remote
    address directly would render a broken image. Falls back to an empty key
    if the download fails.
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
        return ""

    if not data:
        return ""

    from src.utils.storage import LocalStorage

    return LocalStorage().save(data, "featured.jpg", folder="sellers/sample/featured")


async def create_initial_store(
    first_name: str,
    last_name: str,
    store_name: str,
    store_prefix: str,
    phone: str,
):
    """
    Create or update the initial store for production.
    This script is SAFE to run multiple times - it will not delete data.
    """
    # Normalize and validate phone
    phone_normalized = normalize_phone(phone)
    if not validate_ethiopian_phone(phone_normalized):
        raise ValueError(f"Invalid phone number: {phone}")

    phone_h = hash_phone(phone_normalized)

    async with async_session_maker() as session:
        # Check if store already exists
        statement = select(Seller).where(Seller.store_name == store_name)
        result = await session.execute(statement)
        seller = result.scalar_one_or_none()

        if seller:
            print(f"Store '{store_name}' already exists. Updating contact info...")
            seller.phone = encrypt_phone(phone_normalized)
            seller.phone_hash = phone_h
            seller.first_name = first_name
            seller.last_name = last_name
            seller.store_prefix = store_prefix
            seller.featured_image = _store_featured_image()
            seller.business_contact_number = phone_normalized
            session.add(seller)
            await session.commit()
            print(f"Store '{store_name}' updated successfully.")
        else:
            print(f"Creating new store '{store_name}'...")
            seller = Seller(
                first_name=first_name,
                last_name=last_name,
                store_name=store_name,
                store_prefix=store_prefix,
                phone=encrypt_phone(phone_normalized),
                phone_hash=phone_h,
                featured_image=_store_featured_image(),
                business_contact_number=phone_normalized,
            )
            session.add(seller)
            await session.commit()
            print(f"Store '{store_name}' created successfully with prefix '{store_prefix}'.")


def main():
    parser = argparse.ArgumentParser(
        description="Create or update the initial store for production deployment."
    )
    parser.add_argument("--first-name", required=True, help="Store owner first name")
    parser.add_argument("--last-name", required=True, help="Store owner last name")
    parser.add_argument("--store-name", required=True, help="Store name (must be unique)")
    parser.add_argument("--store-prefix", required=True, help="Order prefix (e.g., XCOL)")
    parser.add_argument("--phone", required=True, help="Ethiopian phone number (e.g., 0912345678)")

    args = parser.parse_args()

    asyncio.run(create_initial_store(
        first_name=args.first_name,
        last_name=args.last_name,
        store_name=args.store_name,
        store_prefix=args.store_prefix,
        phone=args.phone,
    ))


if __name__ == "__main__":
    main()
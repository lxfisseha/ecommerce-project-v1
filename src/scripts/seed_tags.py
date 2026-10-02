import asyncio
from sqlmodel import select

# Import every model so SQLModel's metadata registry is populated. Without the
# ones this script does not touch directly, relationships like Product.tags fail
# to resolve when the ORM configures itself.
from src.features.auth.models import Seller, OtpCode  # noqa: F401
from src.features.products.models import (  # noqa: F401
    Product,
    ProductAttribute,
    ProductImage,
    ProductTagLink,
    Tag,
)
from src.features.orders.models import Order, OrderStatusLog  # noqa: F401

from src.database import async_session_maker
from src.features.products.services import ProductService

# Map keywords found in a product name to the tags it should carry.
#
# The keys are ordered and matched with a substring test, so a longer, more
# specific keyword must come before a shorter one it contains: "gym bag" has to
# be tested before "bag", or every gym bag would also be tagged as a handbag.
# The old taxonomy had the same latent problem with "top" inside "gown-adjacent"
# names and no ordering to protect it.
TAG_MAPPING = {
    # Team wear first: "jersey" is specific enough to stand alone.
    ("football jersey", "jersey"): ["football", "jerseys"],

    # Gym-specific before the general apparel terms they contain.
    # "gym" on its own is deliberately not a keyword: it appears in "Gym
    # Gloves", "Gym Tank Top" and "Gym T-Shirt", none of which are bags, and
    # matching it here tagged all three with "bags".
    ("gym fit",): ["apparel", "activewear", "women"],
    ("gym bag",): ["bags", "accessories"],
    ("gym glove", "glove"): ["accessories", "strength"],
    ("gym t-shirt", "t-shirt", "tee"): ["apparel", "activewear", "tops"],

    # Support and training gear.
    ("hand grip", "grip"): ["strength", "accessories"],
    ("knee support", "knee"): ["support", "accessories"],

    # General categories, matched last.
    ("tank top", "tank"): ["apparel", "activewear", "tops"],
    ("underwear", "boxer", "brief"): ["apparel", "underwear"],
    ("short", "legging", "hoodie", "tracksuit", "jacket", "shirt", "top"):
        ["apparel", "activewear"],
    ("shoe", "sneaker", "boot", "trainer"): ["footwear"],
    ("bag", "backpack", "duffel"): ["bags", "accessories"],
    ("leather",): ["premium"],
}

# Applied to every product regardless of the above, so the shop always has
# something to filter on and the grid is never tagless.
ALWAYS_TAGS = ["sportwear"]

async def main():
    async with async_session_maker() as session:
        stmt = select(Product).where(Product.is_deleted == False)
        result = await session.execute(stmt)
        products = result.scalars().all()
        
        print(f"Seeding tags for {len(products)} products...")
        
        seeded_count = 0
        for p in products:
            product_name_lower = p.name.lower()
            tags_to_add = list(ALWAYS_TAGS)

            # Find matching tags. dict preserves insertion order, so the
            # ordering note on TAG_MAPPING is load-bearing.
            for keywords, tags in TAG_MAPPING.items():
                if any(kw in product_name_lower for kw in keywords):
                    tags_to_add.extend(tags)

            # De-duplicate while keeping first-seen order, so a name matching
            # two rules does not create the same tag twice.
            seen = set()
            tags_to_add = [
                t for t in tags_to_add if not (t in seen or seen.add(t))
            ]

            tags_string = ", ".join(tags_to_add)
            print(f"- Seeding '{p.name}' with tags: {tags_string}")
            
            # Fetch with tags relationship loaded
            p_loaded = await ProductService.get_product_by_id(session, p.id)
            await ProductService.sync_product_tags(session, p_loaded, tags_string)
            seeded_count += 1
            
        await session.commit()
        print(f"Successfully seeded tags for {seeded_count} products.")

if __name__ == "__main__":
    asyncio.run(main())

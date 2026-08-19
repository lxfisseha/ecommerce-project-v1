import asyncio
from sqlmodel import select

# Import all models to register them in SQLModel/SQLAlchemy metadata registry
from src.features.auth.models import Seller, OtpCode
from src.features.products.models import Product, ProductImage, ProductAttribute, Tag, ProductTagLink
from src.features.orders.models import Order, OrderStatusLog

from src.database import async_session_maker
from src.features.products.services import ProductService

# Define mapping from keywords in product name to tags list
TAG_MAPPING = {
    ("dress", "kemis", "gown", "skirt", "blouse", "top", "shirt", "jacket"): ["dresses", "apparel", "clothing"],
    ("shoe", "heels", "pumps", "sandals", "flats", "sneakers", "boots"): ["shoes", "footwear"],
    ("handbag", "bag", "tote", "crossbody", "clutch", "shoulder", "wallet"): ["bags", "accessories"],
    ("scarf", "netela", "belt", "jewelry", "necklace", "pendant"): ["accessories", "jewelry"],
    ("habesha", "kemis", "netela"): ["traditional", "ethiopian"],
    ("leather", "silk"): ["premium", "leather"]
}

async def main():
    async with async_session_maker() as session:
        stmt = select(Product).where(Product.is_deleted == False)
        result = await session.execute(stmt)
        products = result.scalars().all()
        
        print(f"Seeding tags for {len(products)} products...")
        
        seeded_count = 0
        for p in products:
            product_name_lower = p.name.lower()
            tags_to_add = []
            
            # Find matching tags
            for keywords, tags in TAG_MAPPING.items():
                if any(kw in product_name_lower for kw in keywords):
                    tags_to_add.extend(tags)
            
            # Default tags if nothing matched
            if not tags_to_add:
                tags_to_add = ["general", "featured"]
                
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

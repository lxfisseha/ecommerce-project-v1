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
    ("shoe", "jordan", "nike"): ["footwear", "streetwear", "shoes"],
    ("dress", "scarf", "jacket", "shirt"): ["apparel", "traditional", "clothing"],
    ("leather", "wallet", "bag", "tote", "messenger"): ["accessories", "leather", "bags"],
    ("cross", "silver", "pendant"): ["jewelry", "traditional", "silver"],
    ("coffee", "beans", "jebena"): ["coffee", "traditional", "organic"],
    ("basket", "storage", "pot", "decor"): ["home", "decor", "handcrafted"],
    ("tv", "tvv"): ["electronics", "appliances"]
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

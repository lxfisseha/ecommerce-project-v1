import asyncio
import random
from src.database import async_session_maker
from src.features.products.models import Product, ProductImage
from src.features.auth.models import Seller
from sqlmodel import select

async def seed_products():
    async with async_session_maker() as session:
        # Get the first seller to associate products with
        result = await session.execute(select(Seller))
        seller = result.scalars().first()
        
        if not seller:
            print("No seller found. Please run add_seller.py first.")
            return

        print(f"Seeding products for seller: {seller.store_name}")

        product_templates = [
            ("Premium Leather Wallet", "Handcrafted genuine Ethiopian leather wallet with multiple card slots.", [450, 650, 800]),
            ("Traditional Handwoven Scarf", "Beautiful handwoven Ethiopian cotton scarf (Netela) with intricate patterns.", [350, 500, 750]),
            ("Organic Coffee Beans", "Single-origin Arabica coffee beans from Yirgacheffe, medium roast.", [280, 350, 420]),
            ("Heritage Leather Tote", "Spacious and durable tote bag made from high-quality vegetable-tanned leather.", [1200, 1500, 1850]),
            ("Modern Habesha Dress", "Contemporary design meeting traditional Ethiopian Habesha Kemis styling.", [2500, 3500, 4500]),
            ("Clay Coffee Pot (Jebena)", "Traditional clay pot used for the Ethiopian coffee ceremony.", [150, 250, 350]),
            ("Spiced Berbere Mix", "Authentic Ethiopian spice blend made with sun-dried chili peppers.", [80, 120, 180]),
            ("Leather Messenger Bag", "Professional messenger bag for laptops and documents, pure leather.", [1800, 2200, 2600]),
            ("Bamboo Storage Basket", "Eco-friendly hand-woven bamboo basket for home organization.", [200, 300, 450]),
            ("Silver Coptic Cross", "Detailed traditional Ethiopian silver cross pendant.", [600, 850, 1100]),
        ]

        images = [
            "https://images.unsplash.com/photo-1627123424574-724758594e93?auto=format&fit=crop&q=80&w=400", # Wallet
            "https://images.unsplash.com/photo-1520903920243-00d872a2d1c9?auto=format&fit=crop&q=80&w=400", # Scarf
            "https://images.unsplash.com/photo-1559056199-641a0ac8b55e?auto=format&fit=crop&q=80&w=400", # Coffee
            "https://images.unsplash.com/photo-1547949003-9792a18a2601?auto=format&fit=crop&q=80&w=400", # Tote
            "https://images.unsplash.com/photo-1589416809000-0618c5256231?auto=format&fit=crop&q=80&w=400", # Dress
            "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&q=80&w=400", # Jebena
            "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?auto=format&fit=crop&q=80&w=400", # Spices
            "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?auto=format&fit=crop&q=80&w=400", # Messenger
            "https://images.unsplash.com/photo-1616489953149-8083ef28255b?auto=format&fit=crop&q=80&w=400", # Basket
            "https://images.unsplash.com/photo-1515562141207-7a88fb7ce338?auto=format&fit=crop&q=80&w=400", # Cross
        ]

        total_to_add = 25
        print(f"Adding {total_to_add} sample products...")

        for i in range(total_to_add):
            template = random.choice(product_templates)
            name = f"{template[0]} #{i+1}"
            description = template[1]
            price = random.choice(template[2])
            
            product = Product(
                seller_id=seller.id,
                name=name,
                description=description,
                price=float(price),
                in_stock=True
            )
            session.add(product)
            await session.flush() # Get product ID

            # Add one main image
            img_url = images[random.randint(0, len(images)-1)]
            img = ProductImage(
                product_id=product.id,
                image_url=img_url,
                image_tag="main"
            )
            session.add(img)

        await session.commit()
        print(f"Successfully added {total_to_add} products.")

if __name__ == "__main__":
    asyncio.run(seed_products())

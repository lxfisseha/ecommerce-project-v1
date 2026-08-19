import argparse
import asyncio
import random
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from src.database import async_session_maker
from src.features.auth.models import Seller
from src.features.orders.models import Order, OrderItem, OrderStatusLog
from src.features.products.models import Product, ProductAttribute, ProductImage, ProductTagLink, Tag

# Each template: (name, description, [prices], {attribute_type: [(value, extra_price), ...]})
product_templates = [
    # --- Ethiopian women's fashion ---
    (
        "Modern Habesha Dress",
        "Contemporary design meeting traditional Ethiopian Habesha Kemis styling, hand-finished with intricate embroidery.",
        [2500, 3500, 4500],
        {
            "Size": [("S", 0), ("M", 0), ("L", 100), ("XL", 200)],
            "Color": [("Ivory", 0), ("Navy", 100), ("Burgundy", 100)],
        },
    ),
    (
        "Habesha Kemis Gown",
        "Full-length traditional Habesha Kemis gown with elegant golden embroidery for special occasions.",
        [3500, 4500, 5800],
        {
            "Size": [("S", 0), ("M", 0), ("L", 150), ("XL", 250)],
            "Color": [("White", 0), ("Ivory", 50), ("Red", 100)],
        },
    ),
    (
        "Netela Traditional Scarf",
        "Beautiful handwoven Ethiopian cotton scarf (Netela) with intricate patterns.",
        [350, 500, 750],
        {
            "Color": [("White", 0), ("Red", 0), ("Mixed", 25)],
            "Size": [("Standard", 0), ("Large", 40)],
        },
    ),
    # --- Dresses ---
    (
        "Printed Maxi Dress",
        "Flowy floor-length maxi dress with a vibrant print, perfect for all-day wear.",
        [900, 1200, 1600],
        {
            "Size": [("S", 0), ("M", 0), ("L", 100), ("XL", 200)],
            "Color": [("Red", 0), ("Blue", 0), ("Green", 0)],
        },
    ),
    (
        "Floral Wrap Dress",
        "Feminine wrap dress with a flattering silhouette and soft floral print.",
        [1100, 1400, 1800],
        {
            "Size": [("S", 0), ("M", 0), ("L", 100), ("XL", 200)],
            "Color": [("Rose", 0), ("Sage", 0), ("Navy", 0)],
        },
    ),
    (
        "Elegant Evening Gown",
        "Show-stopping evening gown with a fitted bodice and flowing skirt.",
        [2000, 2800, 3600],
        {
            "Size": [("S", 0), ("M", 0), ("L", 150), ("XL", 250)],
            "Color": [("Black", 0), ("Navy", 50), ("Burgundy", 100)],
        },
    ),
    (
        "Chiffon Blouse",
        "Lightweight and airy chiffon blouse with a refined, office-ready look.",
        [700, 900, 1200],
        {
            "Size": [("S", 0), ("M", 0), ("L", 80), ("XL", 150)],
            "Color": [("White", 0), ("Cream", 0), ("Sky", 0)],
        },
    ),
    (
        "Tailored Midi Skirt",
        "Chic midi skirt with a tailored fit that pairs perfectly with any top.",
        [800, 1000, 1400],
        {
            "Size": [("S", 0), ("M", 0), ("L", 80), ("XL", 150)],
            "Color": [("Black", 0), ("Beige", 0), ("Burgundy", 50)],
        },
    ),
    (
        "Denim Jacket",
        "Classic denim jacket — a wardrobe staple that layers over any outfit.",
        [1500, 1800, 2200],
        {
            "Size": [("S", 0), ("M", 0), ("L", 100), ("XL", 200)],
            "Color": [("Blue", 0), ("Washed", 0)],
        },
    ),
    # --- Shoes ---
    (
        "Elegant High Heel Shoes",
        "Statement heels that add elegance to every step, from office to evening.",
        [1200, 1600, 2000],
        {
            "Size": [("36", 0), ("37", 0), ("38", 30), ("39", 60), ("40", 90), ("41", 120)],
            "Color": [("Black", 0), ("Beige", 0), ("Burgundy", 50)],
        },
    ),
    (
        "Comfortable Ballet Flat Shoes",
        "Classic ballet flats with cushioned insoles for all-day comfort.",
        [900, 1150, 1400],
        {
            "Size": [("36", 0), ("37", 0), ("38", 30), ("39", 60), ("40", 90), ("41", 120)],
            "Color": [("Black", 0), ("Nude", 0), ("Red", 0)],
        },
    ),
    (
        "Fashion Sandal Shoes",
        "Stylish sandals with adjustable straps — your go-to for warm days.",
        [800, 1100, 1400],
        {
            "Size": [("36", 0), ("37", 0), ("38", 30), ("39", 60), ("40", 90), ("41", 120)],
            "Color": [("Brown", 0), ("Black", 0)],
        },
    ),
    (
        "Trendy Sneaker Shoes",
        "Versatile fashion sneakers that pair with anything, anywhere.",
        [1500, 1900, 2300],
        {
            "Size": [("36", 0), ("37", 0), ("38", 30), ("39", 60), ("40", 90), ("41", 120)],
            "Color": [("White", 0), ("Black", 0)],
        },
    ),
    (
        "Ankle Boot Shoes",
        "Chic ankle boots with a comfortable heel — perfect for cooler seasons.",
        [1800, 2300, 2800],
        {
            "Size": [("36", 0), ("37", 0), ("38", 30), ("39", 60), ("40", 90), ("41", 120)],
            "Color": [("Black", 0), ("Brown", 0)],
        },
    ),
    # --- Bags ---
    (
        "Leather Handbag",
        "Premium genuine leather handbag with multiple compartments and a stylish finish.",
        [1600, 2100, 2600],
        {
            "Color": [("Brown", 0), ("Black", 0)],
            "Style": [("Classic", 0), ("Modern", 100)],
        },
    ),
    (
        "Elegant Clutch Bag",
        "Compact clutch with gold-tone hardware — the perfect evening accessory.",
        [700, 950, 1200],
        {
            "Color": [("Black", 0), ("Gold", 100)],
        },
    ),
    (
        "Crossbody Handbag",
        "Hands-free crossbody bag that keeps your essentials close and secure.",
        [950, 1250, 1600],
        {
            "Color": [("Black", 0), ("Tan", 0), ("Red", 50)],
        },
    ),
    (
        "Structured Shoulder Bag",
        "Clean-lined structured bag that elevates both casual and formal looks.",
        [1400, 1800, 2300],
        {
            "Color": [("Black", 0), ("Beige", 0), ("Navy", 50)],
        },
    ),
    (
        "Canvas Tote Bag",
        "Roomy everyday tote in durable canvas — from work to weekend.",
        [600, 800, 1000],
        {
            "Color": [("Natural", 0), ("Black", 0)],
        },
    ),
    # --- Accessories ---
    (
        "Silk Fashion Scarf",
        "Soft silk scarf that adds a pop of color to any outfit.",
        [400, 550, 750],
        {
            "Color": [("Red", 0), ("Blue", 0), ("Ivory", 0)],
        },
    ),
    (
        "Statement Jewelry Necklace",
        "Bold statement necklace to complete your look for special occasions.",
        [500, 700, 950],
        {
            "Finish": [("Gold", 0), ("Silver", 0)],
        },
    ),
]

images = [
    "https://images.unsplash.com/photo-1595777457583-95e059d581b8?auto=format&fit=crop&q=80&w=400", # Habesha Dress
    "https://images.unsplash.com/photo-1583939003579-730e3918a45a?auto=format&fit=crop&q=80&w=400", # Kemis Gown
    "https://images.unsplash.com/photo-1520903920243-00d872a2d1c9?auto=format&fit=crop&q=80&w=400", # Netela Scarf
    "https://images.unsplash.com/photo-1539008835657-9e8e9680c956?auto=format&fit=crop&q=80&w=400", # Maxi Dress
    "https://images.unsplash.com/photo-1539109136881-3be0616acf4b?auto=format&fit=crop&q=80&w=400", # Wrap Dress
    "https://images.unsplash.com/photo-1566174053879-31528523f8ae?auto=format&fit=crop&q=80&w=400", # Evening Gown
    "https://images.unsplash.com/photo-1567401893414-76b7b1e5a7a5?auto=format&fit=crop&q=80&w=400", # Blouse
    "https://images.unsplash.com/photo-1583496661160-fb5886a0aaaa?auto=format&fit=crop&q=80&w=400", # Midi Skirt
    "https://images.unsplash.com/photo-1551028719-00167b16eac5?auto=format&fit=crop&q=80&w=400", # Denim Jacket
    "https://images.unsplash.com/photo-1543163521-1bf539c55dd2?auto=format&fit=crop&q=80&w=400", # Heels
    "https://images.unsplash.com/photo-1560343090-f0409e92791a?auto=format&fit=crop&q=80&w=400", # Ballet Flats
    "https://images.unsplash.com/photo-1591604466107-ec97de577aff?auto=format&fit=crop&q=80&w=400", # Sandals
    "https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&q=80&w=400", # Sneakers
    "https://images.unsplash.com/photo-1608256246200-53e635b5b65f?auto=format&fit=crop&q=80&w=400", # Ankle Boots
    "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?auto=format&fit=crop&q=80&w=400", # Leather Handbag
    "https://images.unsplash.com/photo-1566150905458-1bf1fc113f0d?auto=format&fit=crop&q=80&w=400", # Clutch
    "https://images.unsplash.com/photo-1594223274512-ad4803739b7c?auto=format&fit=crop&q=80&w=400", # Crossbody
    "https://images.unsplash.com/photo-1584917865442-de89df76afd3?auto=format&fit=crop&q=80&w=400", # Shoulder Bag
    "https://images.unsplash.com/photo-1590874103328-eac38a683ce7?auto=format&fit=crop&q=80&w=400", # Canvas Tote
    "https://images.unsplash.com/photo-1601924994987-69e26d50dc26?auto=format&fit=crop&q=80&w=400", # Silk Scarf
    "https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?auto=format&fit=crop&q=80&w=400", # Necklace
]


def _attribute_rows(template):
    attr_map = template[3] if len(template) > 3 else {}
    rows = []
    for attr_type, options in attr_map.items():
        for value, extra_price in options:
            rows.append((attr_type, value, Decimal(str(extra_price))))
    return rows


def _find_template(name):
    for template in product_templates:
        if name.startswith(template[0]):
            return template
    return None


async def reset_database(session):
    """Delete all catalog + demo order rows in FK-safe order."""
    for table in (OrderStatusLog, OrderItem, Order):
        result = await session.execute(select(table))
        rows = result.scalars().all()
        for row in rows:
            await session.delete(row)
    await session.flush()
    for table in (ProductTagLink, ProductImage, ProductAttribute, Product):
        result = await session.execute(select(table))
        rows = result.scalars().all()
        for row in rows:
            await session.delete(row)
    await session.flush()
    tags = (await session.execute(select(Tag))).scalars().all()
    for tag in tags:
        await session.delete(tag)
    await session.commit()


async def seed_products(reset: bool = False):
    async with async_session_maker() as session:
        if reset:
            await reset_database(session)
            print("Reset complete: cleared old products and demo orders.")

        result = await session.execute(select(Seller))
        seller = result.scalars().first()

        if not seller:
            print("No seller found. Please run add_seller.py first.")
            return

        print(f"Seeding products for seller: {seller.store_name}")

        total_to_add = 25
        print(f"Adding {total_to_add} sample products...")

        for i in range(total_to_add):
            template_index = random.randint(0, len(product_templates) - 1)
            template = product_templates[template_index]
            name = f"{template[0]} #{i+1}"
            description = template[1]
            price = random.choice(template[2])

            product = Product(
                seller_id=seller.id,
                name=name,
                description=description,
                price=float(price),
                in_stock=True,
            )
            session.add(product)
            await session.flush()  # Get product ID

            # Add one main image (matching the template type)
            img_url = images[template_index]
            img = ProductImage(
                product_id=product.id,
                image_url=img_url,
                image_tag="main",
            )
            session.add(img)

            # Add attributes (Size, Color, etc.)
            for attr_type, value, extra_price in _attribute_rows(template):
                session.add(
                    ProductAttribute(
                        product_id=product.id,
                        attribute_type=attr_type,
                        attribute_value=value,
                        extra_price=extra_price,
                    )
                )

        await session.commit()
        print(f"Successfully added {total_to_add} products.")


async def backfill_attributes():
    """Add attributes to existing products that don't have any yet (idempotent)."""
    async with async_session_maker() as session:
        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(Product).options(selectinload(Product.attributes))
        )
        products = result.scalars().all()

        added = 0
        for product in products:
            if product.attributes:
                continue
            template = _find_template(product.name)
            if not template:
                continue

            for attr_type, value, extra_price in _attribute_rows(template):
                session.add(
                    ProductAttribute(
                        product_id=product.id,
                        attribute_type=attr_type,
                        attribute_value=value,
                        extra_price=extra_price,
                    )
                )
            added += 1

        await session.commit()
        print(f"Backfilled attributes for {added} product(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the XCollections demo catalog.")
    parser.add_argument("--reset", action="store_true", help="Delete existing products and demo orders before seeding.")
    args = parser.parse_args()
    asyncio.run(seed_products(reset=args.reset))
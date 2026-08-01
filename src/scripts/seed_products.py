import asyncio
import random
from decimal import Decimal

from sqlalchemy.orm import selectinload
from sqlmodel import select

from src.database import async_session_maker
from src.features.auth.models import Seller
from src.features.products.models import Product, ProductAttribute, ProductImage

# Each template: (name, description, [prices], {attribute_type: [(value, extra_price), ...]})
product_templates = [
    (
        "Premium Leather Wallet",
        "Handcrafted genuine Ethiopian leather wallet with multiple card slots.",
        [450, 650, 800],
        {
            "Color": [("Brown", 0), ("Black", 0), ("Tan", 50)],
            "Style": [("Classic", 0), ("Slim", 30), ("Bifold", 60)],
        },
    ),
    (
        "Traditional Handwoven Scarf",
        "Beautiful handwoven Ethiopian cotton scarf (Netela) with intricate patterns.",
        [350, 500, 750],
        {
            "Color": [("White", 0), ("Black", 0), ("Red", 0), ("Yellow", 0), ("Mixed", 25)],
            "Size": [("Standard", 0), ("Large", 40)],
        },
    ),
    (
        "Organic Coffee Beans",
        "Single-origin Arabica coffee beans from Yirgacheffe, medium roast.",
        [280, 350, 420],
        {
            "Weight": [("250g", 0), ("500g", 120), ("1kg", 260)],
            "Roast": [("Medium", 0), ("Dark", 30)],
        },
    ),
    (
        "Heritage Leather Tote",
        "Spacious and durable tote bag made from high-quality vegetable-tanned leather.",
        [1200, 1500, 1850],
        {
            "Color": [("Brown", 0), ("Black", 0)],
            "Size": [("Medium", 0), ("Large", 150)],
        },
    ),
    (
        "Modern Habesha Dress",
        "Contemporary design meeting traditional Ethiopian Habesha Kemis styling.",
        [2500, 3500, 4500],
        {
            "Size": [("S", 0), ("M", 0), ("L", 0), ("XL", 300)],
            "Color": [("Ivory", 0), ("Navy", 100), ("Burgundy", 100)],
        },
    ),
    (
        "Clay Coffee Pot (Jebena)",
        "Traditional clay pot used for the Ethiopian coffee ceremony.",
        [150, 250, 350],
        {
            "Size": [("Small", 0), ("Medium", 80), ("Large", 150)],
        },
    ),
    (
        "Spiced Berbere Mix",
        "Authentic Ethiopian spice blend made with sun-dried chili peppers.",
        [80, 120, 180],
        {
            "Weight": [("100g", 0), ("250g", 90), ("500g", 160)],
            "Heat": [("Mild", 0), ("Hot", 0)],
        },
    ),
    (
        "Leather Messenger Bag",
        "Professional messenger bag for laptops and documents, pure leather.",
        [1800, 2200, 2600],
        {
            "Color": [("Brown", 0), ("Black", 0)],
            "Size": [("13-inch", 0), ("15-inch", 200)],
        },
    ),
    (
        "Bamboo Storage Basket",
        "Eco-friendly hand-woven bamboo basket for home organization.",
        [200, 300, 450],
        {
            "Size": [("Small", 0), ("Medium", 100), ("Large", 200)],
        },
    ),
    (
        "Silver Coptic Cross",
        "Detailed traditional Ethiopian silver cross pendant.",
        [600, 850, 1100],
        {
            "Size": [("Pendant (2in)", 0), ("Large (3in)", 150)],
            "Finish": [("Polished", 0), ("Antique", 80)],
        },
    ),
]

images = [
    "https://images.unsplash.com/photo-1627123424574-724758594e93?auto=format&fit=crop&q=80&w=400", # Wallet
    "https://images.unsplash.com/photo-1520903920243-00d872a2d1c9?auto=format&fit=crop&q=80&w=400", # Scarf
    "https://images.unsplash.com/photo-1559056199-641a0ac8b55e?auto=format&fit=crop&q=80&w=400", # Coffee
    "https://images.unsplash.com/photo-1547949003-9792a18a2601?auto=format&fit=crop&q=80&w=400", # Tote
    "https://images.unsplash.com/photo-1595777457583-95e059d581b8?auto=format&fit=crop&q=80&w=400", # Dress
    "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&q=80&w=400", # Jebena
    "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?auto=format&fit=crop&q=80&w=400", # Spices
    "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?auto=format&fit=crop&q=80&w=400", # Messenger
    "https://images.unsplash.com/photo-1603532648955-039310d9ed75?auto=format&fit=crop&q=80&w=400", # Basket
    "https://images.unsplash.com/photo-1515562141207-7a88fb7ce338?auto=format&fit=crop&q=80&w=400", # Cross
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


async def seed_products():
    async with async_session_maker() as session:
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

            # Add attributes (Color, Size, etc.)
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
    asyncio.run(seed_products())

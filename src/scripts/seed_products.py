"""
Seed the demo sportwear catalogue.

Each product template is a dict rather than a tuple, and it carries its own
images. The previous layout kept templates and images in two separate lists
indexed against each other, so reordering or removing an entry silently
attached the wrong photo to a product with no error anywhere.

Images come from two sources:

- ``https://...``  a remote stock photo, downloaded at seed time.
- ``local:<name>`` a file in SEED_ASSET_DIR, for products with no usable stock
  photography. Missing files are skipped rather than failing the run, so a
  half-populated assets folder still seeds a usable catalogue.
"""

import argparse
import asyncio
import logging
import random
import urllib.request
from decimal import Decimal
from pathlib import Path

from sqlmodel import select

from src.constants import SITE_NAME
from src.database import async_session_maker
from src.features.auth.models import Seller
from src.features.orders.models import Order, OrderItem, OrderStatusLog
from src.features.products.models import (
    Product,
    ProductAttribute,
    ProductImage,
    ProductTagLink,
    Tag,
)
from src.features.products.services import delete_image_files
from src.utils.storage import LocalStorage

logger = logging.getLogger(__name__)

# Where local seed photos live. Created on demand so a fresh clone seeds fine.
SEED_ASSET_DIR = Path(__file__).resolve().parent.parent / "seed_assets"

# How many units of each template to seed, summing to the catalogue size.
# Products a seller would list once with many variants get fewer units; bulk
# consumables like socks or grips get more.
UNIT_COUNTS = {
    "Leather Gym Gloves": 2,
    "Gym Tank Top": 3,
    "2-Piece Women Gym Fit": 3,
    "Contour Gym Bag": 2,
    "Gym T-Shirt": 3,
    "Arsenal Football Jersey": 2,
    "Manchester United Football Jersey": 2,
    "Manchester City Football Jersey": 2,
    "Premium Modal Underwear": 2,
    "Hand Grip Strengthener": 2,
    "Knee Support Sleeve": 2,
}

# Shared attribute ladders. Apparel runs XS-XXL because the range is unisex and
# S-XL is short for a men's cut; the old catalogue stopped at XL and sized shoes
# on a women's EU 36-41 ladder.
SIZES_APPAREL = [("XS", 0), ("S", 0), ("M", 0), ("L", 0), ("XL", 50), ("XXL", 100)]
SIZES_SHOE = [("40", 0), ("41", 0), ("42", 0), ("43", 50), ("44", 50), ("45", 100)]


def _t(name, description, prices, attributes, images):
    return {
        "name": name,
        "description": description,
        "prices": prices,
        "attributes": attributes,
        "images": images,
    }


def _u(url):
    """A remote stock photo, requested wide enough for the largest variant."""
    return f"{url}?auto=format&fit=crop&q=80&w=1200"


PRODUCT_TEMPLATES = [
    _t(
        "Leather Gym Gloves",
        "Padded leather lifting gloves with wrist wrap. They take load off the bar "
        "and stop the grip blistering on heavy pulls.",
        [900, 1100, 1300],
        {
            "Size": SIZES_APPAREL,
            "Colour": [("Black", 0), ("Brown", 50)],
        },
        ["local:gym-gloves.png"],
    ),
    _t(
        "Gym Tank Top",
        "Lightweight training tank with a loose armhole so the shoulder lifts "
        "cleanly. Holds its shape after washing.",
        [650, 800, 950],
        {
            "Size": SIZES_APPAREL,
            "Colour": [("Black", 0), ("White", 0), ("Blue", 0), ("Pink", 0)],
        },
        [
            _u("https://images.unsplash.com/photo-1605296867724-fa87a8ef53fd"),
            _u("https://images.unsplash.com/photo-1617085606193-6b17105cff2a"),
        ],
    ),
    _t(
        "2-Piece Women Gym Fit",
        "Matching sports bra and leggings in a four-way stretch fabric that stays "
        "opaque when it moves. Sold as a set.",
        [1800, 2200, 2600],
        {
            "Size": SIZES_APPAREL,
            "Colour": [("Black", 0), ("Pink", 0), ("Blue", 50)],
        },
        [
            _u("https://images.unsplash.com/photo-1706029831374-e236f69cbe8b"),
            _u("https://images.unsplash.com/photo-1649888639789-b611bc359d9b"),
        ],
    ),
    _t(
        "Contour Gym Bag",
        "Structured gym bag with a wet compartment and a padded shoulder strap. "
        "Stands up on its own instead of collapsing on the floor.",
        [1400, 1700, 2000],
        {
            "Colour": [("Black", 0), ("Grey", 0), ("Pink", 50)],
            "Size": [("One size", 0)],
        },
        [
            _u("https://images.unsplash.com/photo-1553062407-98eeb64c6a62"),
            _u("https://images.unsplash.com/photo-1708622833152-924c6e364138"),
        ],
    ),
    _t(
        "Gym T-Shirt",
        "Plain training tee in a mid-weight cotton blend. Cut straight so it does "
        "not ride up on presses.",
        [500, 650, 800],
        {
            "Size": SIZES_APPAREL,
            "Colour": [("White", 0), ("Black", 0), ("Navy", 0)],
        },
        [
            _u("https://images.unsplash.com/photo-1521572163474-6864f9cf17ab"),
            _u("https://images.unsplash.com/photo-1581655353564-df123a1eb820"),
        ],
    ),
    _t(
        "Arsenal Football Jersey",
        "Home replica shirt in the classic red and white. Lightweight mesh back "
        "panel so it does not stick to you in a match.",
        [2200, 2600, 3000],
        {
            "Size": [("S", 0), ("M", 0), ("L", 0), ("XL", 100)],
            "Version": [("Home", 0), ("Away", 150)],
        },
        [
            _u("https://images.unsplash.com/photo-1577212017184-80cc0da11082"),
            _u("https://images.unsplash.com/photo-1517466787929-bc90951d0974"),
        ],
    ),
    _t(
        "Manchester United Football Jersey",
        "Home replica shirt in the club's red. Cut with a fuller chest than the "
        "training tops, which run close through the body.",
        [2200, 2600, 3000],
        {
            "Size": [("S", 0), ("M", 0), ("L", 0), ("XL", 100)],
            "Version": [("Home", 0), ("Away", 150)],
        },
        [
            _u("https://images.unsplash.com/photo-1616124619460-ff4ed8f4683c"),
            _u("https://images.unsplash.com/photo-1517466787929-bc90951d0974"),
        ],
    ),
    _t(
        "Manchester City Football Jersey",
        "Home replica shirt in sky blue. Same lightweight mesh as the other kits, "
        "so it stays cool over ninety minutes.",
        [2200, 2600, 3000],
        {
            "Size": [("S", 0), ("M", 0), ("L", 0), ("XL", 100)],
            "Version": [("Home", 0), ("Away", 150)],
        },
        [
            _u("https://images.unsplash.com/photo-1552066379-e7bfd22155c5"),
            _u("https://images.unsplash.com/photo-1641570882851-72738e6e98ee"),
        ],
    ),
    _t(
        "Premium Modal Underwear",
        "Modal blend underwear with a flat seam so it does not mark under a tight "
        "gym short. Sold in packs.",
        [700, 900, 1200],
        {
            "Pack": [("3-pack", 0), ("5-pack", 250)],
            "Colour": [("Black", 0), ("Grey", 0), ("Navy", 0)],
        },
        [
            _u("https://images.unsplash.com/photo-1590490360182-c33d57733427"),
            _u("https://images.unsplash.com/photo-1584467541268-b040f83be3fd"),
        ],
    ),
    _t(
        "Hand Grip Strengthener",
        "Spring-loaded hand gripper for forearm and grip work. Resistance steps up "
        "as you get stronger.",
        [300, 400, 500],
        {
            "Strength": [("Light", 0), ("Medium", 50), ("Heavy", 100)],
        },
        ["local:handgrip.png"],
    ),
    _t(
        "Knee Support Sleeve",
        "Compression sleeve for squats and running. Adds warmth to the joint without "
        "the bulk of a hinged brace.",
        [600, 750, 900],
        {
            "Size": [("S", 0), ("M", 0), ("L", 0)],
            "Support": [("Light", 0), ("Firm", 100)],
        },
        ["local:knee-sleeve.png"],
    ),
]


def _attribute_rows(template):
    """Flatten a template's attribute map into (type, value, extra_price)."""
    rows = []
    for attr_type, options in template["attributes"].items():
        for value, extra_price in options:
            rows.append((attr_type, value, Decimal(str(extra_price))))
    return rows


def _find_template(name):
    """Template whose name prefixes this product name, for backfilling."""
    for template in PRODUCT_TEMPLATES:
        if name.startswith(template["name"]):
            return template
    return None


def _read_local_asset(spec):
    """Read a ``local:<name>`` image from SEED_ASSET_DIR, or None if absent."""
    filename = spec.split(":", 1)[1]
    path = SEED_ASSET_DIR / filename
    if not path.is_file():
        logger.warning(
            "Seed asset %s is missing; %s will be seeded without it. "
            "Expected it at %s", filename, filename, path,
        )
        return None
    return path.read_bytes()


def _store_seed_image(source, index, tag_index):
    """
    Store one seed image and return its object key, or None on failure.

    `source` is a full URL or a ``local:<name>`` spec. Failing one image leaves
    that slot empty rather than aborting the whole seed.
    """
    try:
        if source.startswith("local:"):
            data = _read_local_asset(source)
            if data is None:
                return None
            extension = source.rsplit(".", 1)[-1].lower()
        else:
            request = urllib.request.Request(
                source, headers={"User-Agent": f"{SITE_NAME}-seed/1.0"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
    except Exception as exc:
        logger.warning("Could not fetch seed image %s: %s", source, exc)
        return None

    if not data:
        return None

    return LocalStorage().save(data, f"seed_{index}_{tag_index}.{extension}", folder="products")


async def reset_database(session):
    """
    Delete all catalog + demo order rows in FK-safe order.

    Image files are removed too. Deleting the rows alone would orphan every
    original and variant on disk, since nothing else maps a file back to the
    row that referenced it.
    """
    for table in (OrderStatusLog, OrderItem, Order):
        result = await session.execute(select(table))
        rows = result.scalars().all()
        for row in rows:
            await session.delete(row)
    await session.flush()

    images = (await session.execute(select(ProductImage))).scalars().all()
    for image in images:
        try:
            delete_image_files(image)
        except Exception as exc:
            logger.warning("Could not remove files for image %s: %s", image.id, exc)

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


def _build_unit_queue():
    """
    Flatten UNIT_COUNTS into one entry per unit to create.

    Kept as a queue rather than looping each template independently so the
    resulting catalogue has every product present, which a shop page filtered by
    tag is expected to show.
    """
    queue = []
    for name, count in UNIT_COUNTS.items():
        template = next(
            (t for t in PRODUCT_TEMPLATES if t["name"] == name), None
        )
        if template is None:
            raise ValueError(f"UNIT_COUNTS names an unknown template: {name}")
        queue.extend([template] * count)
    return queue


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

        queue = _build_unit_queue()
        print(f"Adding {len(queue)} products across {len(PRODUCT_TEMPLATES)} lines...")

        pending_images = []
        missing_images = 0

        for i, template in enumerate(queue):
            name = f"{template['name']} #{i + 1}"
            price = random.choice(template["prices"])

            product = Product(
                seller_id=seller.id,
                name=name,
                description=template["description"],
                price=float(price),
                in_stock=True,
            )
            session.add(product)
            await session.flush()  # Get product ID

            # Store every image for this product, exactly as a multi-image
            # upload would: the first is "main" and drives the grid and hero,
            # the rest are "gallery" and feed the carousel. display_order keeps
            # the carousel in the order the photos were listed.
            for tag_index, source in enumerate(template["images"]):
                object_name = _store_seed_image(source, i, tag_index)
                if not object_name:
                    missing_images += 1
                    continue
                img = ProductImage(
                    product_id=product.id,
                    object_name=object_name,
                    image_tag="main" if tag_index == 0 else "gallery",
                    display_order=tag_index,
                )
                session.add(img)
                await session.flush()
                pending_images.append(img.id)

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
        print(f"Successfully added {len(queue)} products.")

        if missing_images:
            print(
                f"Note: {missing_images} image(s) could not be stored. Those "
                "products are listed without them."
            )

        # Generate WebP variants for the seeded images, same as an upload.
        from src.scripts.process_images import enqueue_image_processing

        queued = 0
        for image_id in pending_images:
            try:
                enqueue_image_processing(image_id)
                queued += 1
            except Exception as exc:
                logger.warning("Could not enqueue image %s: %s", image_id, exc)
        if queued:
            print(f"Queued {queued} images for variant generation.")


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
    parser = argparse.ArgumentParser(description=f"Seed the {SITE_NAME} demo catalog.")
    parser.add_argument("--reset", action="store_true", help="Delete existing products and demo orders before seeding.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_products(args.reset))
    asyncio.run(backfill_attributes())

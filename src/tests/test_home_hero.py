import pytest
import pytest_asyncio
from datetime import timedelta
from sqlmodel import select
from src.features.auth.models import Seller
from src.utils.datetime import utc_now
from src.tests.conftest import client, maker

SELLER1_IMG = "https://res.cloudinary.com/dpimwr1pr/image/upload/v1/hero_old.jpg"
SELLER3_IMG = "https://res.cloudinary.com/dpimwr1pr/image/upload/v1/hero_new.jpg"


@pytest.mark.asyncio
async def test_home_uses_most_recently_updated_seller_image():
    async with maker() as session:
        seller1 = (await session.execute(select(Seller).where(Seller.id == 1))).scalar_one()
        seller1.featured_image = SELLER1_IMG
        seller1.updated_at = utc_now() - timedelta(hours=1)

        seller3 = Seller(
            id=3, first_name="Seller", last_name="Three", store_name="Store Three",
            store_prefix="ST3", phone="ENC_P", phone_hash="HASH_3",
            featured_image=SELLER3_IMG, updated_at=utc_now(),
        )
        session.add(seller3)
        await session.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    assert "hero_new.jpg" in resp.text
    assert "hero_old.jpg" not in resp.text


@pytest.mark.asyncio
async def test_first_seller_wins_when_it_is_newest():
    async with maker() as session:
        seller1 = (await session.execute(select(Seller).where(Seller.id == 1))).scalar_one()
        seller1.featured_image = SELLER1_IMG
        seller1.updated_at = utc_now()

        seller3 = Seller(
            id=3, first_name="Seller", last_name="Three", store_name="Store Three",
            store_prefix="ST3", phone="ENC_P", phone_hash="HASH_3",
            featured_image=SELLER3_IMG, updated_at=utc_now() - timedelta(hours=1),
        )
        session.add(seller3)
        await session.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    assert "hero_old.jpg" in resp.text
    assert "hero_new.jpg" not in resp.text

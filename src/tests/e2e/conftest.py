"""
E2E test fixtures for StoreLedger.

Starts a real Uvicorn server with a test SQLite database, seeds sample data,
and provides Playwright browser pages for each test.
"""

import os
import asyncio
import re
import socket
import tempfile
import threading
import time
from decimal import Decimal

import pytest
import uvicorn
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel


@pytest.fixture(autouse=True)
def _db_setup_teardown():
    """Shadow src/tests/conftest.py's unit-test DB fixture.

    E2E tests run against their own Uvicorn server + seeded SQLite DB managed
    by the _e2e_server fixture below, so the parent autouse fixture (which
    overrides get_session and reseeds a separate database) must not run here.
    """
    yield

# ---------------------------------------------------------------------------
# Test database setup — SQLite file in temp dir, shared across the session
# ---------------------------------------------------------------------------
_db_file = os.path.join(tempfile.gettempdir(), f"e2e_test_{os.getpid()}.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{_db_file}"

def _find_free_port() -> int:
    """Return an available TCP port by binding a temporary socket."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


E2E_PORT = _find_free_port()
BASE_URL = f"http://localhost:{E2E_PORT}"

# When set, E2E tests run against a deployed (hosted) app instead of the local
# Uvicorn server + seeded SQLite DB. Used by src/tests/e2e/test_hosted_smoke.py.
E2E_HOST_BASE_URL = os.environ.get("E2E_HOST_BASE_URL", "").strip()

def _build_engine():
    # NullPool: the seed runs in the main thread's asyncio loop while Uvicorn
    # serves in a different thread/loop. aiosqlite connections are loop-bound,
    # so never reuse pooled connections across loops.
    return create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )


engine = _build_engine()
TestSessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Override the FastAPI get_session dependency BEFORE importing the app
# ---------------------------------------------------------------------------
async def _override_get_session():
    async with TestSessionMaker() as session:
        yield session


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------
async def _seed_database():
    """Create tables and insert a seller + sample products."""
    from src.features.auth.models import Seller, OtpCode  # noqa: F401
    from src.features.products.models import (  # noqa: F401
        Product,
        ProductImage,
        ProductAttribute,
        Tag,
        ProductTagLink,
    )
    from src.features.orders.models import (  # noqa: F401
        Order,
        OrderItem,
        OrderSequence,
        OrderStatusLog,
    )
    from src.utils.crypto import encrypt_phone, hash_phone

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    async with TestSessionMaker() as session:
        # --- Seller ---
        seller = Seller(
            id=1,
            first_name="Test",
            last_name="Seller",
            store_name="TestStore",
            store_prefix="TST",
            phone=encrypt_phone("911000000"),
            phone_hash=hash_phone("911000000"),
        )
        session.add(seller)
        await session.flush()

        # --- Tags ---
        tags = {}
        for tag_name, tag_slug in [
            ("Dresses", "dresses"),
            ("Shoes", "shoes"),
            ("Handbags", "handbags"),
            ("Accessories", "accessories"),
        ]:
            tag = Tag(name=tag_name, slug=tag_slug)
            session.add(tag)
            await session.flush()
            tags[tag_slug] = tag

        # --- Products (15 in-stock + 2 out-of-stock) ---
        products_data = [
            ("Elegant Maxi Dress", Decimal("2500.00"), True, "dresses", "Flowing maxi dress with a modern silhouette"),
            ("Modern Habesha Dress", Decimal("3200.00"), True, "dresses", "Handwoven traditional Ethiopian dress"),
            ("Printed Floral Dress", Decimal("1800.00"), True, "dresses", "Lightweight floral print summer dress"),
            ("Silk Evening Gown", Decimal("4500.00"), True, "dresses", "Elegant silk gown for special occasions"),
            ("Chiffon Blouse", Decimal("1200.00"), True, "dresses", "Sheer chiffon blouse, office ready"),
            ("Elegant High Heel Shoes", Decimal("2200.00"), True, "shoes", "Statement high heels for evenings out"),
            ("Comfortable Ballet Flats", Decimal("1500.00"), True, "shoes", "Classic ballet flats, all-day comfort"),
            ("Trendy Sneaker Shoes", Decimal("1600.00"), True, "shoes", "Casual sneakers for everyday wear"),
            ("Fashion Sandal Shoes", Decimal("1200.00"), True, "shoes", "Strappy fashion sandals for warm days"),
            ("Leather Ankle Boots", Decimal("2800.00"), True, "shoes", "Genuine leather ankle boots"),
            ("Leather Handbag", Decimal("3000.00"), True, "handbags", "Spacious genuine leather handbag"),
            ("Elegant Clutch Bag", Decimal("1500.00"), True, "handbags", "Sleek clutch for nights out"),
            ("Canvas Tote Bag", Decimal("800.00"), True, "handbags", "Everyday canvas tote, roomy and light"),
            ("Silk Fashion Scarf", Decimal("600.00"), True, "accessories", "Soft silk scarf with a classic print"),
            ("Pearl Necklace", Decimal("900.00"), True, "accessories", "Timeless pearl necklace"),
            # Out-of-stock products
            ("Sold Out Evening Dress", Decimal("9999.00"), False, "dresses", "This product is out of stock"),
            ("Unavailable High Heels", Decimal("5000.00"), False, "shoes", "These shoes are unavailable"),
        ]

        from src.utils.datetime import utc_now
        from datetime import timedelta

        # Assign staggered created_at timestamps so the product list's
        # created_at DESC ordering is deterministic: Elegant Maxi Dress
        # (id 1) is the newest and appears on page 1, older products fall
        # onto later pages.
        base_time = utc_now() - timedelta(hours=len(products_data))
        for i, (name, price, in_stock, tag_slug, desc) in enumerate(products_data):
            product = Product(
                seller_id=1,
                name=name,
                description=desc,
                price=price,
                in_stock=in_stock,
                is_deleted=False,
                created_at=base_time + timedelta(hours=len(products_data) - i),
            )
            session.add(product)
            await session.flush()

            # Add a placeholder image so templates don't break
            img = ProductImage(
                product_id=product.id,
                image_url="https://placehold.co/400x400/e2e8f0/64748b?text=Test",
                image_tag="main",
            )
            session.add(img)

            # Link tag
            link = ProductTagLink(product_id=product.id, tag_id=tags[tag_slug].id)
            session.add(link)

        # Add attributes to the first product (for attribute selection tests)
        await session.flush()
        for attr_type, attr_value, extra in [
            ("Color", "Black", Decimal("0.00")),
            ("Color", "White", Decimal("0.00")),
            ("Size", "M", Decimal("0.00")),
            ("Size", "L", Decimal("100.00")),
        ]:
            attr = ProductAttribute(
                product_id=1,
                attribute_type=attr_type,
                attribute_value=attr_value,
                extra_price=extra,
            )
            session.add(attr)

        await session.commit()


# ---------------------------------------------------------------------------
# Uvicorn server in a background thread
# ---------------------------------------------------------------------------
class _ServerThread(threading.Thread):
    """Runs Uvicorn in a daemon thread so pytest can control its lifecycle."""

    def __init__(self):
        super().__init__(daemon=True)
        self.server = None

    def run(self):
        from src.main import app
        from src.database import get_session
        from src.utils.storage import CloudinaryService
        from src.utils.sms import AfroMessageService

        # E2E has no real Cloudinary credentials. Stub upload/delete so the
        # seller product add/edit/delete flows run against the real UI without
        # making network calls.
        CloudinaryService.upload_image = staticmethod(
            lambda content, folder="products", eager=None: (
                "https://placehold.co/400x400/e2e8f0/64748b?text=E2E"
            )
        )
        CloudinaryService.delete_image = staticmethod(lambda public_id: None)

        # Never hit the real SMS provider from tests; the OTP is read straight
        # from SQLite anyway.
        async def _send_otp_sms(phone_number, otp_code):
            return True

        async def _send_order_notifications_sms(
            buyer_phone, seller_phone, order_id, total_amount, item_summary
        ):
            return {"buyer_success": True, "seller_success": True}

        AfroMessageService.send_otp_sms = staticmethod(_send_otp_sms)
        AfroMessageService.send_order_notifications_sms = staticmethod(
            _send_order_notifications_sms
        )

        app.dependency_overrides[get_session] = _override_get_session

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=E2E_PORT,
            log_level="warning",
            lifespan="off",  # we manage tables ourselves
        )
        self.server = uvicorn.Server(config)
        self.server.run()

    def stop(self):
        if self.server:
            self.server.should_exit = True


# ---------------------------------------------------------------------------
# Session-scoped: start server once, seed DB, tear down at end
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def _e2e_server():
    """Start a real HTTP server for the entire E2E test session.

    When E2E_HOST_BASE_URL is set, yield the hosted URL directly instead of
    seeding a local DB and starting a Uvicorn thread (used by the hosted
    smoke tests, which are read-only).
    """
    if E2E_HOST_BASE_URL:
        yield E2E_HOST_BASE_URL
        return

    # Seed the database before starting the server
    asyncio.run(_seed_database())

    server_thread = _ServerThread()
    server_thread.start()

    # Wait for the server to be ready
    import httpx

    for _ in range(40):
        try:
            r = httpx.get(f"{BASE_URL}/", timeout=1.0)
            if r.status_code < 500:
                break
        except (httpx.ConnectError, httpx.ReadError):
            pass
        time.sleep(0.25)
    else:
        pytest.fail("E2E server did not start within 10 seconds")

    yield BASE_URL

    server_thread.stop()
    # Cleanup DB file
    try:
        asyncio.run(engine.dispose())
    except Exception:
        pass
    try:
        if os.path.exists(_db_file):
            os.remove(_db_file)
    except PermissionError:
        pass


# ---------------------------------------------------------------------------
# Playwright fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Use installed Edge browser channel for instant execution without downloading large binaries."""
    return {**browser_type_launch_args, "channel": "msedge"}


@pytest.fixture(scope="session")
def base_url(_e2e_server):
    """Expose the base URL to tests."""
    return _e2e_server


@pytest.fixture
def page(browser, base_url):
    """
    Provide a fresh Playwright browser page for each test.
    Sets a default navigation timeout and viewport.
    """
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        base_url=base_url,
    )
    context.set_default_timeout(15_000)  # 15s timeout
    pg = context.new_page()
    yield pg
    pg.close()
    context.close()


@pytest.fixture
def skip_hosted():
    """Skip a test in hosted mode (read-only smoke checks against the deploy).

    Tests that need the local seeded SQLite DB (OTP reading, deterministic
    seeded products/attributes) can't run against the deployed app.
    """
    if E2E_HOST_BASE_URL:
        pytest.skip("Local seeded DB only; not applicable in hosted mode")
    yield


# ---------------------------------------------------------------------------
# Seller login helpers — the login flow is phone + OTP, and the OTP is stored
# in plaintext in the DB, so tests read the latest code straight from SQLite.
# ---------------------------------------------------------------------------
def fetch_latest_otp(phone: str) -> str | None:
    """Return the newest unused OTP code for a phone (as stored by the server)."""
    from sqlmodel import select
    from src.features.auth.models import OtpCode
    from src.utils.crypto import hash_phone
    from src.utils.phone import normalize_phone

    phone = normalize_phone(phone)
    phone_h = hash_phone(phone)

    async def _read():
        async with TestSessionMaker() as session:
            stmt = (
                select(OtpCode)
                .where(OtpCode.phone_hash == phone_h)
                .where(OtpCode.used == False)  # noqa: E712
                .order_by(OtpCode.created_at.desc())
            )
            row = (await session.execute(stmt)).scalars().first()
            return row.code if row else None

    # pytest-asyncio may already have a running loop in this thread, so run the
    # coroutine on a dedicated thread with its own fresh event loop instead of
    # calling asyncio.run() directly (which raises "already running").
    result: dict[str, str | None] = {}

    def _run_in_thread():
        result["code"] = asyncio.run(_read())

    t = threading.Thread(target=_run_in_thread)
    t.start()
    t.join()
    return result.get("code")


def _fill_otp(page, code: str) -> None:
    """Fill the six single-digit OTP boxes and let the page JS sync the hidden field."""
    for i, ch in enumerate(code):
        page.locator(f'input[name="otp_{i}"]').fill(ch)


@pytest.fixture(scope="session")
def seller_storage_state(browser, base_url):
    """
    Log in once as the seeded seller (phone 911000000) and capture the session
    cookies so all seller tests reuse an authenticated context instead of
    burning the /auth/login rate limit on every test.
    """
    if E2E_HOST_BASE_URL:
        pytest.skip(
            "Hosted mode: seller login needs the local seeded DB (OTP is sent "
            "via real SMS on the hosted app)"
        )

    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        base_url=base_url,
    )
    context.set_default_timeout(15_000)
    pg = context.new_page()

    pg.goto("/auth/login")
    pg.locator('input[name="phone"]').fill("911000000")
    pg.locator('button[type="submit"]:has-text("Send OTP")').click()

    # Wait for the OTP verification partial to replace the auth container.
    pg.locator('input[name="otp_0"]').wait_for(state="visible")

    code = fetch_latest_otp("911000000")
    assert code, "No OTP was generated for the seeded seller"

    _fill_otp(pg, code)
    pg.locator('button[type="submit"]:has-text("Verify & Login")').click()

    # The server responds with HX-Redirect: /dashboard (307 → /dashboard/).
    pg.wait_for_url(re.compile(r"/dashboard/?$"))
    assert "/dashboard" in pg.url

    state = context.storage_state()
    pg.close()
    context.close()
    return state


@pytest.fixture
def seller_page(browser, seller_storage_state, base_url):
    """
    Fresh page for each test, seeded with the seller's stored session cookies.
    """
    context = browser.new_context(
        storage_state=seller_storage_state,
        viewport={"width": 1280, "height": 720},
        base_url=base_url,
    )
    context.set_default_timeout(15_000)
    pg = context.new_page()
    yield pg
    pg.close()
    context.close()

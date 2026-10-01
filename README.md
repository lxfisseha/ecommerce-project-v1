# XCollections — Single-Seller E-Commerce Platform

A production-grade e-commerce backend for Ethiopian merchants. phone/OTP authentication, product catalog with image management, order lifecycle with state-machine enforcement, anonymous checkout, and a seller dashboard — all served via server-rendered HTML with HTMX interactivity.

**Stack:** Python 3.12 · FastAPI · PostgreSQL (asyncpg/SQLModel) · Jinja2 · HTMX · TailwindCSS · Docker (Caddy) · Redis/RQ · Pillow · AfroMessage SMS

**Status:** v1.0 — feature-complete, 154 passing tests, deployed on Docker with Caddy terminating TLS.

---

## Features at a Glance

| Area | Capabilities |
|------|-------------|
| **Auth** | Passwordless OTP login via phone + SMS. Session cookies (7 day expiry). Rate-limited (5 POST/min). |
| **Products** | Full CRUD with image upload, rich attributes (brand, color, size, weight), tag-based categorization, stock toggle. |
| **Shop** | Public product grid with search, sort (price/name/newest), tag filter, pagination (12/page). Out-of-stock items hidden. |
| **Checkout** | Anonymous single-item checkout with phone/name/address capture. PII encrypted at rest (AES-256-GCM). |
| **Orders** | Auto-generated IDs (`ET-{prefix}-{YYYYMMDD}-{0001}`). State-machine enforced lifecycle (pending→confirmed→shipped→delivered). SMS buyer notification on confirmation. |
| **Dashboard** | Stats (total/sold/active products, pending/total orders), order list with search/filter/status updates, profile management. |
| **Security** | CSRF protection (double-submit cookie + HMAC), rate limiting (in-memory sliding window), session middleware, PII encryption. |

Full feature breakdown → [docs/features_v2.md](docs/features_v2.md)

---

## Quick Start

### Prerequisites

- Docker + Docker Compose (for the standard deployment)
- PostgreSQL 16+ (bundled as a compose service)
- AfroMessage API key (SMS) — optional for local dev

Images need no third-party account: they are stored on the local filesystem
and resized in a background worker.

### Installation

```bash
# Clone and enter
git clone <repo-url> && cd xcollections

# Configure environment
cp .env.example .env
# Edit .env: SECRET_KEY, POSTGRES_PASSWORD, AFROMESSAGES_API_KEY

# Build and start the full stack (app, worker, postgres, redis, caddy)
docker compose up -d

# Apply migrations
docker compose exec app alembic upgrade head

# Seed a store and a sample catalog
docker compose exec app python src/scripts/add_seller.py
docker compose exec app python src/scripts/seed_products.py
```

The app is served on https://localhost with a self-signed Caddy certificate.

### Run without Docker

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
source .venv/bin/activate # macOS/Linux

pip install -r requirements.txt
alembic upgrade head
python src/scripts/add_seller.py
uvicorn src.main:app --reload --port 8765
```

Without Redis there is no worker, so uploads keep their original file and
templates serve that until you start `rq worker` yourself.

---

## Architecture

```
┌─────────────┐    ┌─────────────────────────────────────────────┐
│   Browser   │◄──►│              FastAPI (Uvicorn)               │
│ (HTMX+Alpine)│   │  ┌──────┐ ┌──────┐ ┌──────────┐ ┌───────┐  │
└─────────────┘    │  │Session│ │ CSRF │ │RateLimit │ │Routes │  │
                   │  │Middleware│ │Middleware│ │Middleware│ │       │
                   │  └──────┘ └──────┘ └──────────┘ └───────┘  │
                   │         │                      │            │
                   │    ┌────┴──────────────────────┘            │
                   │    │  Service Layer (services/)             │
                   │    └────────┬───────────────────────────────┘
                   │             │                               │
                   │    ┌────────▼────────┐                     │
                   │    │  SQLModel ORM   │                     │
                   │    └────────┬────────┘                     │
                   └─────────────┼───────────────────────────────┘
                                 │
                     ┌────────────▼────────────┐
                     │     PostgreSQL 16        │
                     │       (asyncpg)          │
                     └─────────────────────────┘

        ┌────────────────────────┐        ┌──────────────────────────┐
        │  Worker (RQ) + Pillow  │◄──►Redis│   Storage: local volume │
        │  writes 3 WebP sizes   │        │   media_data:/app/media │
        └────────────────────────┘        └───────────┬──────────────┘
                                                       │ served at /media
                                                       ▼
                                              Caddy (TLS, cache headers)
```

External services: **AfroMessage** (SMS OTP + order notifications), **Telegram** (fallback OTP delivery). Images are self-hosted — originals are written to a Docker volume and a background worker generates 160/400/800 WebP variants into the same volume, which Caddy serves with immutable cache headers.

### Image pipeline

```
upload ──► products/originals/<uuid>.<ext>   (written synchronously)
       └─► enqueue RQ job
              └─► worker: Pillow resize ──► processed/products/<uuid>_{160,400,800}w.webp
                                            recorded in product_images.processed_urls
```

Templates resolve an image through the `media_url` filter, which picks the nearest generated width and falls back to the original while a job is still pending. Deleting a product removes both the original and its variants.

`MEDIA_ROOT` must be a persistent volume. With Compose, `media_data` is already mounted into both `app` and `worker`; if you override it, mount the same volume in both or the worker will not see uploads.

Full architecture → [docs/architecture_v2.md](docs/architecture_v2.md)

---

## API Overview

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/` | No | Home page (8 latest products) |
| GET | `/shop` | No | Product grid with search/filter/pagination |
| GET | `/product/{id}` | No | Product detail |
| GET | `/checkout/{id}` | No | Checkout form |
| POST | `/checkout/{id}` | No | Place order |
| GET | `/order/{ref}` | No | Order confirmation |
| POST | `/auth/login` | No | Request OTP |
| POST | `/auth/verify-otp` | No | Verify OTP → session |
| GET | `/dashboard` | Seller | Dashboard stats |
| GET/POST | `/dashboard/products/...` | Seller | Product CRUD |
| GET | `/dashboard/orders` | Seller | Order list + search |
| POST | `/dashboard/orders/{id}/status` | Seller | Update order status |
| GET/POST | `/dashboard/profile` | Seller | Profile management |

Full API reference → [docs/api_v2.md](docs/api_v2.md)

---

## Testing

```bash
# Run all tests
pytest src/tests/ -q

# Run with coverage
pytest src/tests/ --cov=src --cov-report=term-missing

# Run specific module
pytest src/tests/ -q -k auth
```

**154 tests** across auth, products, orders, checkout, CSRF, rate limiting, concurrency, seller onboarding, and the image pipeline. SQLite in-memory via session override in conftest.py.

---

## Deployment

The app runs as a set of Docker Compose services. Caddy terminates TLS and proxies to the app. Key environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | 32+ byte key for sessions + CSRF |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `AFROMESSAGES_API_KEY` | No | AfroMessage SMS API key |
| `AFROMESSAGES_FROM` | No | SMS sender ID |
| `MEDIA_ROOT` | No | Image storage root, defaults to `/app/media` |
| `REDIS_URL` | No | RQ queue, defaults to `redis://redis:6379` |
| `AUTH_CHEAT_PIN` | No | Skip OTP. **Development only — never set in production.** |

The `media_data` volume must be owned by uid 999, which is the app's user in the image:

```bash
docker run --rm -v xcollections_media_data:/m caddy:2-alpine chown -R 999:999 /m
```

### Operations

```bash
docker compose ps                          # service health
docker compose logs -f app                 # app log
docker compose logs -f worker              # job log
docker compose exec app alembic upgrade head
docker compose exec app python -m src.scripts.process_images <image_id>   # re-run one image
```

Full deployment guide → [docs/deployment_v2.md](docs/deployment_v2.md)

---

## Project Structure

```
src/
├── main.py                 # FastAPI application factory
├── database.py             # Async engine + session factory
├── config.py               # Pydantic Settings from .env
├── middleware/
│   ├── session.py          # Session cookie management
│   ├── csrf.py             # Double-submit cookie CSRF
│   └── rate_limit.py       # In-memory sliding window limiter
├── utils/
│   ├── storage.py          # LocalStorage: read/write/delete image files
│   ├── crypto.py           # AES-256-GCM PII encryption
│   └── phone.py            # Ethiopian phone normalisation
├── features/
│   ├── auth/               # Login, OTP, session
│   ├── buyer/              # Home, shop, checkout, order confirmation
│   ├── dashboard/          # Seller dashboard, orders, profile
│   ├── orders/             # Order service + state machine
│   └── products/           # Product CRUD, image upload
├── scripts/
│   ├── process_images.py   # RQ worker: generates 160/400/800 WebP variants
│   ├── add_seller.py       # Sample seller
│   └── seed_products.py    # Sample catalog (downloads images locally)
├── templates/              # Jinja2 templates
│   ├── base.html           # Public layout
│   ├── buyer/              # Shop, product detail, checkout partials
│   ├── dashboard/          # Seller dashboard templates
│   └── products/           # Product form + list partials
└── tests/                  # 154 tests
    ├── conftest.py         # Shared fixtures + session override
    ├── test_image_processing.py    # Variant widths, WebP output, transparency
    ├── test_media_content_type.py  # /media content types + cache headers
    ├── test_templates_config.py    # media_url filter behaviour
    ├── test_products*.py   # Product CRUD tests
    ├── test_orders*.py     # Order lifecycle tests
    └── test_csrf.py        # CSRF protection tests
```

---

## License

Private — all rights reserved.

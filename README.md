# StoreLedger — Single-Seller E-Commerce Platform

A production-grade e-commerce backend for Ethiopian merchants. phone/OTP authentication, product catalog with image management, order lifecycle with state-machine enforcement, anonymous checkout, and a seller dashboard — all served via server-rendered HTML with HTMX interactivity.

**Stack:** Python 3.12 · FastAPI · PostgreSQL (asyncpg/SQLModel) · Jinja2 · HTMX · TailwindCSS · Cloudinary · AfroMessage SMS

**Status:** v1.0 — feature-complete, 95 passing tests, deployed on Vercel + Supabase.

---

## Features at a Glance

| Area | Capabilities |
|------|-------------|
| **Auth** | Passwordless OTP login via phone + SMS. Session cookies (7 day expiry). Rate-limited (6 POST/min). |
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

- Python 3.12+
- PostgreSQL 16+ (or Supabase account)
- Cloudinary account (image hosting)
- AfroMessage API key (SMS) — optional for local dev

### Installation

```bash
# Clone and enter
git clone <repo-url> && cd storeledger

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate    # Windows
source .venv/bin/activate # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials (see docs/deployment_v2.md)
```

### Database Setup

```bash
# Create the database
createdb storeledger

# Run migrations
alembic upgrade head

# Seed a seller account
python -c "from src.scripts.seed import seed_seller; seed_seller()"
```

### Run

```bash
uvicorn src.main:app --reload --port 8765
```

Open http://localhost:8765 — the login page renders. Use the phone number you seeded to log in via OTP.

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
                    │  (Supabase / asyncpg)    │
                    └─────────────────────────┘
```

External services: **Cloudinary** (image upload/serve), **AfroMessage** (SMS OTP + order notifications), **Telegram** (fallback OTP delivery).

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

**95 tests** across auth, products, orders, checkout, CSRF, rate limiting, concurrency, and seller onboarding. SQLite in-memory via session override in conftest.py.

---

## Deployment

The app is designed for **Vercel (serverless)** with **Supabase PostgreSQL**. Key environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | 32+ byte key for sessions + CSRF |
| `DATABASE_URL` | Yes | PostgreSQL async connection string |
| `CLOUDINARY_URL` | Yes | Cloudinary API URL |
| `AFROMESSAGES_API_KEY` | No | AfroMessage SMS API key |
| `AFROMESSAGES_FROM` | No | SMS sender ID |

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
│   ├── templates.py        # Jinja2 environment
│   ├── encryption.py       # AES-256-GCM PII encryption
│   └── response.py         # Response helpers (HX-Redirect, etc.)
├── features/
│   ├── auth/               # Login, OTP, session
│   ├── buyer/              # Home, shop, checkout, order confirmation
│   ├── dashboard/          # Seller dashboard, orders, profile
│   ├── orders/             # Order service + state machine
│   └── products/           # Product CRUD, image upload
├── scripts/
│   └── seed.py             # Seller seeding utility
├── templates/              # Jinja2 templates
│   ├── base.html           # Public layout
│   ├── seller_base.html    # Dashboard layout
│   ├── login_partial.html  # Login page
│   ├── 404.html            # Not found
│   └── 500.html            # Server error
└── tests/                  # 15 files, 95 tests
    ├── conftest.py         # Shared fixtures + session override
    ├── test_auth*.py       # Auth flow tests
    ├── test_products*.py   # Product CRUD tests
    ├── test_orders*.py     # Order lifecycle tests
    ├── test_shop*.py       # Buyer grid tests
    ├── test_checkout*.py   # Checkout flow tests
    ├── test_csrf.py        # CSRF protection tests
    ├── test_rate_limiter.py # Rate limit tests
    └── test_onboarding.py  # Seller setup tests
```

---

## License

Private — all rights reserved.

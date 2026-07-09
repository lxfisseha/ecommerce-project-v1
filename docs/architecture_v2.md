# Architecture

System architecture, component relationships, request lifecycle, and data flow for the StoreLedger platform.

---

## Layered Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Presentation Layer                      │
│  Jinja2 Templates · Server-Rendered HTML · HTMX · Alpine  │
└───────────────────────┬──────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────┐
│                    Application Layer                       │
│  FastAPI Routes (features/*/routes.py)                    │
│  Middleware: Session → CSRF → RateLimit                   │
│  Request validation via Pydantic (POST bodies, query)     │
└───────────────────────┬──────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────┐
│                    Service Layer                           │
│  orders/services.py  ·  auth/services.py                  │
│  Business logic: order lifecycle, OTP generation,         │
│  notification dispatch, order ID generation               │
└───────────────────────┬──────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────┐
│                    Data Access Layer                       │
│  SQLModel Models (features/*/models.py)                   │
│  AsyncSession · Raw SQL for stats queries                 │
│  AES-256-GCM encryption for PII columns                   │
└───────────────────────┬──────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────┐
│                    Data Store                              │
│  PostgreSQL 16 (Supabase) · asyncpg driver                │
│  Alembic migrations · 12 versions                         │
└──────────────────────────────────────────────────────────┘
```

---

## Middleware Stack

Requests pass through three middleware layers **in order** before reaching route handlers.

```
Incoming Request
      │
      ▼
┌─────────────┐
│   Session   │  Reads session cookie → attaches seller_id to request.state
│  Middleware  │  Creates session if none exists
└──────┬──────┘
       │
       ▼
┌─────────────┐
│     CSRF     │  Validates X-CSRF-Token header against session cookie
│  Middleware  │  Skips validation for GET/HEAD/OPTIONS + multipart/form-data
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  RateLimit  │  Sliding-window counter per IP (X-Forwarded-For)
│  Middleware  │  Limits: 6 POST/min (auth), 11 POST/min (checkout)
└──────┬──────┘
       │
       ▼
   Route Handler
```

**Source files:**
- `src/middleware/session.py` — SessionManager class, cookie set/read/clear
- `src/middleware/csrf.py` — CSRFProtectMiddleware, HMAC-SHA256 token generation
- `src/middleware/rate_limit.py` — RateLimitMiddleware, in-memory dict with deque

---

## Request Lifecycle (Example: Checkout)

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Browser  │    │ FastAPI  │    │  Session │    │  CSRF    │    │  Rate    │
│ (HTMX)   │    │  Router  │    │  Middle  │    │  Middle  │    │  Limit   │
└────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘
     │               │               │               │               │
     │  1. POST /checkout/{id}       │               │               │
     │  + form data                  │               │               │
     │  + X-CSRF-Token               │               │               │
     ├──────────────►│               │               │               │
     │               │  2. Process session cookie   │               │
     │               ├──────────────►│               │               │
     │               │  3. Session OK (or new)      │               │
     │               │◄──────────────┤               │               │
     │               │  4. Validate CSRF token     │               │
     │               ├──────────────►│               │               │
     │               │  5. CSRF valid               │               │
     │               │◄──────────────┤               │               │
     │               │  6. Check rate limit         │               │
     │               ├──────────────────────────────►│               │
     │               │  7. Under limit               │               │
     │               │◄──────────────────────────────┤               │
     │               │                               │               │
     │               │  8. Route handler: buyer/routes.py            │
     │               │     - Validate form data                      │
     │               │     - Verify product exists & in stock        │
     │               │     - Encrypt PII fields                      │
     │               │     - Call OrderService.create_order           │
     │               │     - Generate order ID                       │
     │               │     - Create Order + OrderStatusLog           │
     │               │     - Send SMS notification                   │
     │               │     - Redirect to /order/{ref}                │
     │               │                               │               │
     │  9. 302 Redirect + HX-Redirect header        │               │
     │◄──────────────┤                               │               │
     │               │                               │               │
     │ 10. GET /order/{ref}                         │               │
     ├──────────────►│ (passes through middleware)   │               │
     │               │     - Render confirmation page               │
     │◄──────────────┤                               │               │
     │               │                               │               │
```

---

## Database Entity Relationships

```
┌───────────┐     ┌─────────────────────┐
│  Seller   │     │    OtpCode          │
│───────────│     │─────────────────────│
│ id (PK)   │◄────│ seller_id (FK)      │
│ phone     │     │ code                │
│ store_name│     │ expires_at          │
│ store_    │     │ attempts            │
│  prefix   │     │ used                │
│ display_  │     └─────────────────────┘
│  name     │
└──────┬────┘
       │
       │ 1
       │
       │ *
       ▼
┌─────────────────────┐
│      Product        │
│─────────────────────│
│ id (PK)             │
│ seller_id (FK)      │
│ name, description   │
│ price               │
│ stock               │
│ is_active           │
│ category            │
└──────┬─────────┬────┘
       │         │
       │ 1       │ 1
       │         │
       │ *       │ *
       ▼         ▼
┌────────────┐  ┌────────────────────┐
│ Product    │  │ ProductAttribute   │
│ Image      │  │────────────────────│
│────────────│  │ id (PK)            │
│ id (PK)    │  │ product_id (FK)    │
│ product_id │  │ brand              │
│ image_url  │  │ color              │
│ public_id  │  │ size               │
│ is_main    │  │ weight             │
│ tag        │  └────────────────────┘
└────────────┘
       │
       │
       │ (through ProductTagLink)
       │
       ▼
┌────────────┐
│    Tag     │
│────────────│
│ id (PK)    │
│ name       │
└────────────┘

┌──────────────────────┐
│       Order          │
│──────────────────────│
│ id (PK)              │
│ product_id (FK)      │
│ seller_id (FK)       │
│ customer_name        │
│ customer_phone (enc) │
│ address (enc)        │
│ quantity             │
│ status (enum)        │
│ order_id (unique)    │
│ created_at           │
└──────────┬───────────┘
           │
           │ 1
           │
           │ *
           ▼
┌──────────────────────┐
│   OrderStatusLog     │
│──────────────────────│
│ id (PK)              │
│ order_id (FK)        │
│ from_status          │
│ to_status            │
│ changed_by           │
│ changed_at           │
└──────────────────────┘
```

---

## Route Module Organization

```
src/features/
├── auth/
│   ├── __init__.py
│   ├── routes.py       # POST /login, /verify-otp, /resend-otp, /logout
│   ├── services.py     # send_otp, verify_otp, create_session
│   └── models.py       # Seller, OtpCode
│
├── buyer/
│   ├── __init__.py
│   ├── routes.py       # GET /, /shop, /checkout/{id}, /order/{ref}
│   │                   # POST /checkout/{id}
│   └── __init__.py     # (empty, no services or models)
│
├── dashboard/
│   ├── __init__.py
│   ├── routes.py       # GET /dashboard, /dashboard/orders,
│   │                   # GET/POST /dashboard/orders/{id}/status,
│   │                   # GET /dashboard/profile, POST /dashboard/profile
│   └── __init__.py     # (empty)
│
├── orders/
│   ├── __init__.py
│   ├── routes.py       # (routes are in dashboard/ and buyer/)
│   ├── services.py     # OrderService, NotificationService
│   └── models.py       # Order, OrderStatusLog
│
├── products/
│   ├── __init__.py
│   ├── routes.py       # GET/POST /dashboard/products/add,
│   │                   # GET/POST /dashboard/products/{id}/edit,
│   │                   # POST /dashboard/products/{id}/delete,
│   │                   # POST /dashboard/products/{id}/toggle-stock,
│   │                   # POST /dashboard/products/{id}/upload-image,
│   │                   # POST /dashboard/products/{id}/delete-image,
│   │                   # POST /dashboard/products/{id}/set-main-image
│   ├── services.py     # (Cloudinary image upload logic inline in routes)
│   └── models.py       # Product, ProductImage, ProductAttribute,
│                       # Tag, ProductTagLink
│
└── scripts/
    └── seed.py         # seed_seller() utility
```

---

## External Service Integrations

```
┌─────────────────┐
│   Cloudinary     │  Image storage and CDN
│                  │  - Product image upload (image_tag parameter)
│                  │  - Automatic deletion on product delete
│                  │  - Public URL generation for templates
│  Library:        │
│  cloudinary      │
│  (cloudinary-)   │
│  python SDK      │
└─────────────────┘

┌──────────────────┐
│  AfroMessage SMS │  SMS delivery for OTP and order notifications
│                  │  - OTP codes via SMS
│                  │  - Order confirmation SMS to buyers
│                  │  - POST requests to AfroMessage API
│  Protocol:       │
│  HTTP POST       │
│  (no SDK)        │
└──────────────────┘

┌──────────────────┐
│  Telegram Bot    │  Fallback OTP delivery channel
│                  │  - Mirror of SMS OTP
│                  │  - Configured per-seller with TELEGRAM_ID
│  Protocol:       │
│  HTTP POST to    │
│  Bot API         │
└──────────────────┘
```

---

## Security Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Security Layers                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ 1. Session Authentication                                 │
│    - Random UUID session ID stored in HttpOnly cookie     │
│    - Server-side session map (dict[session_id, Seller])   │
│    - 7-day expiry (max_age=604800)                       │
│    - Secure flag enabled when request.is_secure           │
│                                                          │
│ 2. CSRF Protection                                        │
│    - Double-submit cookie pattern                         │
│    - Token = HMAC-SHA256(session_id, purpose_key)         │
│    - Token in cookie matches X-CSRF-Token header          │
│    - Exempt: GET/HEAD/OPTIONS + multipart/form-data       │
│                                                          │
│ 3. Rate Limiting                                          │
│    - In-memory sliding window (deque of timestamps)       │
│    - Keyed by X-Forwarded-For or client host              │
│    - Per-endpoint limits (configurable dict)              │
│    - Response: 429 + Retry-After header                  │
│                                                          │
│ 4. PII Encryption                                         │
│    - AES-256-GCM via cryptography library                 │
│    - Encrypted fields: customer_phone, address on Order   │
│    - Encrypted at rest, decrypted on read for dashboard   │
│    - Encryption key derived from SECRET_KEY               │
│                                                          │
│ 5. Input Validation                                       │
│    - Pydantic models for all POST/query parameters        │
│    - HTML escaping via Jinja2 autoescaping                │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Error Handling

```
Global Exception Handler (main.py)
           │
           │
     ┌─────▼─────┐
     │  HTTPException │
     └─────┬─────┘
           │
     ┌─────┴─────┐
     │  Known    │         ┌──────────────┐
     │  errors   │────────►│ Render error │
     │  (401,    │         │   template   │
     │   403,    │         │  with status │
     │   404,    │         └──────────────┘
     │   429)    │
     └───────────┘
           │
     ┌─────▼─────┐
     │  Unknown  │         ┌──────────────┐
     │  errors   │────────►│ Render 500   │
     │  (500)    │         │  template +  │
     └───────────┘         │  log trace   │
                           └──────────────┘
```

- **404:** Templates/rendered `404.html`
- **500:** Templates/rendered `500.html`
- **401:** Redirect to `/auth/login`
- **403:** Redirect to `/auth/login` (with message)
- **429:** `Retry-After` header + plain text message

---

## Template Hierarchy

```
base.html                    # Public layout: navbar, footer, container
├── index.html               # Home page (8 latest products)
├── shop.html                # Full product grid
├── product_detail.html      # Single product view
├── checkout.html            # Checkout form
├── order_confirmation.html  # Post-purchase confirmation
├── login_partial.html       # Login page
├── 404.html                 # Not found
└── 500.html                 # Server error

seller_base.html             # Dashboard layout: sidebar, top bar
├── dashboard.html           # Stats overview
├── orders.html              # Order list with search/filter
├── order_detail.html        # Single order with status controls
├── products.html            # Product list
├── add_product.html         # Product creation form
├── edit_product.html        # Product edit form
└── profile.html             # Seller profile form
```

Rendering is done via Jinja2 with `Templates` from `jinja2` using `FileSystemLoader('templates')`. Templates use TailwindCSS CDN for styling and HTMX for dynamic interactions (status updates, search, inline edits).

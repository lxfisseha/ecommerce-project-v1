# Engineering Practices

Code organization, patterns, conventions, and testing approach used in the StoreLedger codebase.

---

## Code Organization

### Feature-Based Module Layout

```
src/
├── main.py                  # App factory, middleware, exception handler
├── database.py              # AsyncEngine + session factory
├── config.py                # Pydantic Settings (reads .env)
├── middleware/              # Cross-cutting concerns
│   ├── session.py
│   ├── csrf.py
│   └── rate_limit.py
├── utils/                   # Shared utilities
│   ├── templates.py
│   ├── encryption.py
│   └── response.py
├── features/                # Business domains
│   ├── auth/
│   │   ├── routes.py        # HTTP handlers only
│   │   ├── services.py      # Business logic
│   │   └── models.py        # SQLModel ORM models
│   ├── buyer/               # (similar pattern)
│   ├── dashboard/
│   ├── orders/
│   └── products/
├── scripts/
│   └── seed.py
├── templates/
└── tests/
    ├── conftest.py
    └── test_*.py
```

**Principle:** Each feature module owns its routes, business logic, and database models. Routes are thin — they validate input, call services, and return responses. Services contain all business logic.

---

## Patterns

### 1. Service Layer Pattern

Routes delegate to service classes or functions. Services are stateless and accept `AsyncSession` as a parameter.

```python
# Route (thin)
@router.post("/checkout/{product_id}")
async def place_order(product_id: UUID, data: CheckoutForm = Depends(), db: AsyncSession = Depends(get_session)):
    product = await product_service.get_by_id(db, product_id)
    order = await OrderService.create_order(db, seller_id=product.seller_id, ...)
    return RedirectResponse(url=f"/order/{order.order_id}", status_code=303)

# Service (business logic)
class OrderService:
    @staticmethod
    async def create_order(db: AsyncSession, ...) -> Order:
        # validate, encrypt PII, generate order_id, create Order + OrderStatusLog, send SMS
```

**Where this pattern breaks:** Product image upload logic (Cloudinary API calls) lives directly in the route handler rather than a service layer. This is an inconsistency.

---

### 2. Dependency Injection via FastAPI Depends()

```python
async def get_session():
    async with AsyncSession(engine) as session:
        yield session

# Route usage
async def dashboard(request: Request, db: AsyncSession = Depends(get_session)):
```

---

### 3. Middleware Stack Pattern

Three middleware classes, each with a single responsibility, applied in order:

```python
app.add_middleware(SessionMiddleware)
app.add_middleware(CSRFProtectMiddleware)
app.add_middleware(RateLimitMiddleware)
```

Each middleware implements `__init__(app)` + `__call__(scope, receive, send)` and delegates to the next middleware via `app(scope, receive, send)`.

---

### 4. Session Authentication

Custom session implementation (no third-party library):

```python
# Session storage
session_store: Dict[str, Seller] = {}

# Session middleware reads cookie → looks up seller → attaches to request.state
request.state.seller = session_store.get(session_id)
```

Session cookies:
- Name: `session_id`
- Value: random UUID
- HttpOnly: True
- Secure: True when HTTPS
- Max-Age: 604800 (7 days)

---

### 5. CSRF Double-Submit Cookie

```python
# Token generation
token = hmac.new(
    key=derive_key(purpose),
    msg=session_id.encode(),
    digestmod=hashlib.sha256
).hexdigest()

# Verification on mutating requests
token_from_cookie == token_from_header
```

The cookie is set on every response. The client reads it and sends it back as `X-CSRF-Token` header (handled by HTMX and inline JavaScript).

---

### 6. Rate Limiting (Sliding Window)

```python
class RateLimitMiddleware:
    limits: Dict[str, int] = {  # path_pattern → max_requests
        "auth": 6,      # POST /auth/* — 6 per 60s
        "checkout": 11, # POST /checkout/* — 11 per 60s
        "default": 60,  # everything else
    }
    histories: Dict[str, deque] = {}  # ip → deque of timestamps
```

On each request: purge timestamps older than 60s, count remaining, reject if over limit.

---

## Database Patterns

### AsyncSession Lifecycle

```python
# Via dependency injection (per-request session)
async def get_session():
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
```

### Raw SQL for Aggregates

Stats queries use raw SQL for performance:

```python
result = await db.execute(text("""
    SELECT
        (SELECT COUNT(*) FROM products WHERE seller_id = :sid) as total_products,
        (SELECT COUNT(*) FROM orders WHERE seller_id = :sid AND status IN ('shipped','delivered')) as sold_products
"""), {"sid": seller_id})
```

### PII Encryption/Decryption

```python
class Order(SQLModel, table=True):
    customer_phone: str = Field(sa_type=String, ...)  # encrypted at rest

    # Encrypt before insert
    @validator("customer_phone", pre=True, always=True)
    def encrypt_phone(cls, v):
        return encrypt(v) if v and not v.startswith("gcm:") else v
```

Note: Encryption is applied at the application layer via Pydantic validators, not at the database level.

---

## Testing Patterns

### Test Configuration

- **Database:** SQLite in-memory (`aiosqlite`)
- **Session override:** `conftest.py` overrides `get_session` dependency
- **External services:** All mocked (Cloudinary, AfroMessage, Telegram)
- **Rate limiting:** Disabled in tests (separate test file for rate limiter)

```python
# conftest.py
@pytest.fixture
def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False})
    # ... create tables, yield session, drop tables

# Override the app's dependency
app.dependency_overrides[get_session] = db_session
```

### Test Structure

```
src/tests/
├── conftest.py                          # Shared fixtures
├── test_auth_login.py                   # Login flow
├── test_auth_verify_otp.py              # OTP verification
├── test_products_crud.py                # Product create/read/update/delete
├── test_products_image_upload.py        # Image upload + deletion
├── test_shop_browsing.py               # Public shop
├── test_shop_checkout.py               # Checkout flow
├── test_orders_create.py               # Order creation
├── test_orders_status_transitions.py    # State machine transitions
├── test_dashboard_orders.py            # Dashboard order views
├── test_dashboard_stats.py             # Dashboard stats
├── test_seller_onboarding.py           # Seller seed/setup
├── test_encryption.py                  # PII encryption/decryption
├── test_csrf.py                        # CSRF protection
├── test_rate_limiter.py                # Rate limit middleware
├── test_concurrent_orders.py           # Concurrency safety
```

### Test Patterns

**Arrange-Act-Assert** with async/await:

```python
async def test_create_order_success(db_session, test_product):
    # Arrange
    seller = await create_test_seller(db_session)
    product = await create_test_product(db_session, seller.id)

    # Act
    order = await OrderService.create_order(
        db=db_session,
        seller_id=seller.id,
        product_id=product.id,
        customer_name="Test User",
        customer_phone="+251911111111",
        address="Test Address",
        quantity=1,
    )

    # Assert
    assert order.status == OrderStatus.PENDING
    assert order.order_id.startswith(f"ET-{seller.store_prefix}-")
```

**Client fixture** for full request/response testing:

```python
async def test_checkout_page_renders(async_client, test_product):
    response = await async_client.get(f"/checkout/{test_product.id}")
    assert response.status_code == 200
    assert "Buy Now" in response.text
```

---

## Error Handling

### Global Exception Handler

```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    if isinstance(exc, HTTPException):
        # known errors → render appropriate template
        if exc.status_code == 404:
            return HTMLResponse(templates.render("404.html"), status_code=404)
        if exc.status_code in (401, 403):
            return RedirectResponse(url="/auth/login")
        if exc.status_code == 429:
            return PlainTextResponse("Rate limit exceeded", status_code=429, headers=...)
    # Unknown → log and render 500
    logger.exception("Unhandled error")
    return HTMLResponse(templates.render("500.html"), status_code=500)
```

### HTMX Error Handling

The `HX-Redirect` response header is used for redirects after form submissions (instead of standard 302), allowing HTMX to follow the redirect via AJAX:

```python
return HTMLResponse(
    content='<div id="message">Success</div>',
    headers={"HX-Redirect": "/dashboard/orders"}
)
```

---

## Conventions

| Concern | Convention |
|---------|-----------|
| Imports | stdlib → third-party → local, grouped and alphabetized |
| Async | All DB operations use async/await |
| Session management | Via `request.state.seller` (set by middleware) |
| IDs | UUID for primary keys, custom `order_id` for public reference |
| Templates | Jinja2 with `templates` global in `src/utils/templates.py` |
| Static assets | Cloudinary URLs (no local static files) |
| Configuration | Pydantic `BaseSettings` from `.env` |
| Response types | HTML via Jinja2 templates, `RedirectResponse`, or HTMX-specific headers |

---

## Known Technical Debt

1. **Cloudinary logic in routes** — Image upload/delete calls are in the product route handler rather than a service
2. **In-memory session store** — Sessions are lost on server restart; suitable for single-instance but not horizontal scaling
3. **No persistent rate limit store** — Rate limit counters reset on restart; attackers can bypass by cycling IPs
4. **Inline encryption validator** — PII encryption is triggered by a Pydantic model validator, making it implicit
5. **SQLite incompatibility** — `statement_cache_size=0` connect_arg prevents running the full app on SQLite locally

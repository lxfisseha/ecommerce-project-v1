# AleMart Code Review

**Project:** Single-seller e-commerce platform for Ethiopian merchants  
**Stack:** FastAPI + PostgreSQL (SQLModel) + Jinja2 + HTMX + TailwindCSS  
**Date:** June 2026  
**Reviewer:** Senior Software Engineer

---

## Production Readiness Summary

The project is **not ready for production**. While the core architecture is sound and several security-conscious decisions have been made, there are critical gaps in authentication hardening, error handling, infrastructure, and testing that would cause real-world problems. The project is at a **solid alpha stage** — functional for development/demo, but requiring meaningful work before serving real customers and handling real money-equivalent transactions.

**Estimated effort to production: 2-4 weeks** (assuming full-time work by one engineer).

---

## Ratings

| Area | Rating | Summary |
|------|--------|---------|
| **Security** | 6/10 | Good encryption practices, derived keys per purpose, SECRET_KEY forced via validator, but `decrypt_data` has no legacy fallback (shows `[encrypted]` on old records), no buyer CSRF on checkout, ORM objects mutated with plaintext |
| **Performance** | 7/10 | N+1 queries partially handled via selectinload, pagination on product list, seller_id filters removed (single-vendor eliminates redundant WHERE clauses), no caching yet |
| **Code Quality** | 7/10 | Clean domain separation, consistent style, but duplicated logic across features and incomplete error handling |
| **Design Patterns** | 7/10 | Solid domain-driven layout, service layer pattern, HTMX for interactivity — but inconsistent auth boundary enforcement |
| **Testing** | 4/10 | Coverage is emerging (14 test files) but **stale tests exist** (cross-seller isolation tests should have been removed with seller_id filtering), `test_product_search.py` creates an orphan FK reference (`seller_id=2` with no seller 2), no conftest, order-dependent, no CI, no end-to-end tests |

**Overall: 6/10** — Functional foundation with multiple production-blocking gaps. Recent improvements (single-vendor operation, backward-compatible crypto) are positive, but `decrypt_data` lacking a legacy fallback, stale tests, and ORM plaintext mutation need immediate attention.

---

## Security

### Strengths

- **AES-256 encryption for PII**: Phone numbers and delivery addresses are encrypted at rest via Fernet (AES-256) with per-field HMAC-SHA256 hashes for lookup (`src/utils/crypto.py:36-44`). This is a correct pattern — encrypt for confidentiality, hash for indexed lookups.
- **CSRF protection**: Custom middleware (`src/middleware/csrf.py`) protects all non-GET methods with token validation via cookie-header comparison.
- **Rate limiting**: Tiered sliding-window rate limiter (`src/middleware/rate_limit.py`) with stricter limits on auth endpoints (5 POST/min), checkout submission (10 POST/min), and global fallback (120/min).
- **OTP attempt limiting**: 3 attempts per OTP code (`src/features/auth/services.py:77`), 5-minute expiry, rate-limited to 5 OTP requests/hour.
- **Query parameterization**: All SQLAlchemy queries use parameterized `.where()` — no SQL injection risk.
- **Templates auto-escape**: Jinja2 auto-escaping via `{{ }}` prevents XSS.

### Critical Issues

#### 1. No database connection encryption enforcement
`src/database.py:7-14` connects to PostgreSQL via `asyncpg`. The `DATABASE_URL` contains credentials in plaintext. No mention of SSL/TLS enforcement (`?sslmode=require`). On a network path without encryption, database traffic (including queries containing PII) is transmitted in cleartext.

#### 2. `decrypt_data` has no legacy fallback — existing records show `[encrypted]`
`src/utils/crypto.py:42-52`: When `decrypt_data` fails with the current Fernet key (because the data was encrypted before `derive_key("encryption")` was introduced), it returns the literal string `"[encrypted]"`. The `legacy_decrypt_data` function exists at line 54 but is **never used as a fallback** inside `decrypt_data`. This means:
- Dashboard profile page shows `+251[encrypted]` for the seller's phone
- Dashboard order detail shows `[encrypted]` for buyer phone and delivery address
- Order confirmation page shows `[encrypted]` for the same fields

**Fix**: Add a try/except in `decrypt_data` that falls back to `legacy_decrypt_data` before returning `"[encrypted]"`.

#### 3. Email and address fields not validated
`Seller.business_email` is stored as a plain `Optional[str]` with `max_length=255` — no email format validation. Similarly, `delivery_address` is encrypted but never structurally validated. Malformed or excessively long inputs reach the database.

### Medium Issues

- `src/middleware/csrf.py:60-61` notes that multipart form CSRF validation is **not fully implemented** — it relies on the header/query fallback. The existing product add/edit forms use `multipart/form-data` (for image uploads) and pass the CSRF token in a query parameter (`?csrf_token=...`), which appears in server logs and browser history.
- No security headers (`Content-Security-Policy`, `X-Frame-Options`, `Strict-Transport-Security`) set on responses.
- No input sanitization on product `name` or `description` fields beyond the empty check.

---

## Performance

### Strengths

- **Eager loading via selectinload**: All product queries use `selectinload` to fetch images, attributes, and tags in fewer queries.
- **Async throughout**: FastAPI async handlers, async database sessions, async HTTP calls for SMS — good for I/O-bound workloads.
- **Background SMS dispatch**: `orders/services.py:80` uses `asyncio.create_task()` to fire SMS notifications without blocking the checkout response.

### Critical Issues

#### 1. Database `echo=True` in production
`src/database.py:9`: `echo=True` causes SQLAlchemy to log every SQL statement. In production this generates enormous log volume and can leak query contents (including PII in WHERE clauses after decryption in application code). **Fix**: Make configurable via `settings`.

#### 2. No connection pooling limits
`src/database.py:7-14`: The engine is created with `pool_pre_ping=True` and `pool_recycle=3600`, but no explicit `pool_size` or `max_overflow` are set. Under moderate load, the pool could exhaust database connections.

### Medium Issues

- No Redis/memcached cache layer. Every product page hit queries the database.
- No image optimization beyond Cloudinary's default. No thumbnail generation strategy.
- `echo=True` on the engine means every `SELECT` is printed to stdout — adds overhead even in development.

---

## Code Quality

### Strengths

- **Clean domain separation**: Features are organized into `auth/`, `products/`, `orders/`, `buyer/`, `dashboard/` — each with its own `routes.py`, `services.py`, and `models.py`.
- **Consistent naming**: Class names, method names, and variable names follow clear conventions.
- **Docstrings on non-trivial methods**: Several service methods have useful docstrings explaining purpose and side effects.
- **HTMX patterns are consistent**: The shop page search and the new product search follow identical HTMX patterns.
- **Good use of type hints**: Most functions have type annotations.

### Issues

#### 1. Inconsistent authorization patterns
- `dashboard/routes.py` uses a `get_current_seller()` function that returns `None` if not authenticated, then each handler checks `if not seller:` with a redirect.
- `products/routes.py` uses `Depends(require_seller_id)` which raises HTTPException(303).
- `buyer/routes.py` has no auth at all.

Three different patterns for three different feature modules. The new `src/dependencies.py` starts to unify this but `dashboard/routes.py` still uses the local function.

#### 2. Repeated error handling blocks
In `products/routes.py:add_product`, the same template-response-with-error pattern repeats 6+ times. While seller re-fetching has been extracted to the session, the error handling blocks still duplicate the same response structure. This violates DRY and makes the route function excessively long.

#### 3. Lazy imports scattered through route code
Multiple files import dependencies inside route functions rather than at the top of the file:
- `products/routes.py:203`: `from .models import ProductImage`
- `buyer/routes.py:20`: `from src.features.auth.models import Seller`
- `buyer/routes.py:140`: `from src.utils.phone import ...`
- `buyer/routes.py:191`: `from src.utils.crypto import decrypt_data`
- `main.py:64`: `from fastapi.responses import RedirectResponse`

These are presumably to avoid circular imports, but the pattern should be addressed at the module level instead.

#### 4. `CloudinaryService` unused imports
`src/utils/storage.py:5-7` duplicates the import of `cloudinary`, `cloudinary.uploader`, `src.config.settings`, and imports `urlparse` but already has them on lines 1-4. Dead code.

#### 5. ORM objects mutated with plaintext data
Multiple routes decrypt data in-place on ORM objects for template rendering:
- `src/features/dashboard/routes.py:107-108`: `order.buyer_phone = decrypt_data(...)` — mutates the ORM object. If a later commit occurs (it doesn't currently), plaintext would be persisted.
- `src/features/buyer/routes.py:193-194`: Same pattern for order confirmation.

This is currently safe because the session is not committed after mutation, but it's fragile — adding a commit elsewhere could leak plaintext into the database.

#### 6. No buyer registration/onboarding flow
The entire seller registration path is missing. New sellers cannot sign up through the application. They must be added manually via `src/scripts/add_seller.py` or direct database insertion. This is a significant functional gap for a multi-seller platform.

#### 7. Magic numbers
- `delivery_fee = 150` appears in `routes.py:100` and `services.py:160` — should be a constant.
- `MAX_SIZE = 5 * 1024 * 1024` appears in multiple route handlers.
- Image tag indices (`image_tag_0`, etc.) are hardcoded as strings.

---

## Design Patterns

### Strengths

- **Service layer**: Business logic is separated into `*Service` classes rather than living in route handlers. This makes testing easier (the search tests call `ProductService.search_products()` directly).
- **Domain-driven structure**: Features are grouped by domain (auth, products, orders) rather than by layer (controllers, models, views).
- **HTMX over JS framework**: The project uses HTMX for interactivity rather than a heavy SPA framework, which simplifies the backend and keeps the template-rendering paradigm consistent.
- **Soft deletes**: Products use `is_deleted` rather than hard deletion, preserving referential integrity with orders.
- **Audit logging**: `OrderStatusLog` tracks every status change with old/new values, changed_by, and context.

### Issues

#### 1. Feature modules are not truly independent
There are cross-feature imports throughout:
- `products/services.py` references `Tag` from its own module (fine).
- `dashboard/routes.py` imports `Order`, `OrderStatusLog`, `OrderService` from `orders`, and `Product` from `products`.
- `buyer/services.py` imports `Product`, `Tag`, `ProductTagLink` from `products`.

This isn't inherently wrong, but it means changes to one domain's models ripple through others. Consider defining shared interfaces or read models if cross-feature coupling grows.

#### 2. No repository pattern
Services directly construct SQLAlchemy queries. While acceptable for a project this size, introducing a repository layer would:
- Isolate ORM-specific code
- Make unit testing faster (mock repositories instead of databases)
- Allow swapping storage backends

#### 3. Authentication/authorization is not centralized
Currently, auth enforcement happens at the route handler level with different patterns. A more robust approach would use:
- **Middleware-level auth**: Check session on every request (except public routes) before it reaches the handler.
- **Permission-based access**: The current system is binary (logged in vs. not). There's no role model.

#### 4. Order ID generation has a race condition
`src/features/orders/services.py:116-121`: The `generate_order_id` method uses `SELECT COUNT(*) WHERE order_id LIKE 'ET-{prefix}-{today}-%'` to compute the next sequence number. Under concurrent requests, two orders could get the same sequence number. **Fix**: Use a database sequence, `SELECT ... FOR UPDATE`, or a distributed ID generator.

#### 5. Templates are not using component patterns
Several patterns repeat across templates (product cards, stock toggles, empty states). The product card appears in `_product_list_content.html` and `_product_grid.html` — identical HTML duplicated. Should be extracted to a shared partial like `products/_product_card.html`.

#### 6. Order ID generation still seller-scoped but prefix could be in session
`generate_order_id` at `orders/services.py:108` fetches the entire `Seller` row from DB just to get `store_prefix`. Since `seller_name` and `store_name` are already stored in the session at login, `store_prefix` could also be stored there, eliminating a redundant DB hit on every order.

#### 7. Buyer checkout has no CSRF enforcement
The checkout form at `buyer/routes.py:124` is a POST endpoint that accepts orders, but the buyer-facing templates don't explicitly include or validate CSRF tokens for buyer submissions. The CSRF middleware *would* catch it if the cookie and header match, but the buyer's page HTML doesn't include the token in forms. This relies entirely on the cookie matching pattern.

---

## Testing

### Strengths

- **25 new product search tests** covering service layer, route layer (HTMX and full page), and pagination.
- **Overall 81 tests** covering login, CSRF, products, orders, tags, profile, buyer search, edge cases, SMS, and audit logging.
- **Tests use in-memory SQLite** for fast, isolated runs.
- **Service-layer tests** exist alongside route-level tests.

### Issues

#### 1. No `conftest.py`
Every test file duplicates the same ~15 lines of engine/session/client setup. A shared `conftest.py` would eliminate this boilerplate and ensure consistent configuration.

```python
# Missing: conftest.py with shared fixtures for:
# - async engine/session
# - TestClient
# - seed seller
# - csrf helper
```

#### 2. Tests are order-dependent
Running all tests in sequence vs. individually produces different results. The `test_login.py` failures in bulk runs (rate-limited to 429 instead of expected 403/200) prove that tests share global state (the in-memory rate limiter and the CSRF middleware's cookie). Additionally, `test_profile.py` tests send POST requests without CSRF tokens and expect `303` but receive `403`, because the CSRF middleware blocks requests without tokens. This is a pre-existing test isolation issue affecting 4 profile tests.

#### 3. No pytest configuration file
No `pytest.ini`, `pyproject.toml` section, or `setup.cfg` defines asyncio mode. The tests work via `pytest-asyncio` defaults, but explicit configuration prevents ambiguity:
```ini
[pytest]
asyncio_mode = auto
```

#### 4. Missing test coverage
| Area | Coverage |
|------|----------|
| Auth login/OTP | ✓ (basic) |
| Product CRUD | ✓ (basic) |
| Product search | ✓ (new, comprehensive) |
| Buyer search | ✓ (comprehensive) |
| Orders | Partial (audit, ID gen, status flow tested) |
| Checkout | Partial (no tests for validation errors re-rendering form) |
| Dashboard | Minimal (profile update tested) |
| Rate limiter | None |
| CSRF middleware | None |
| SMS fallback | ✓ |
| Image upload failure paths | None |

#### 5. Stale tests — cross-seller isolation tests still exist (CONFIRMED FAILING)
`src/tests/test_edge_cases.py:94-110`: `test_cross_seller_protection` overrides `get_current_seller_id` to `2` and expects `404` when Product A (seller_id=1) is accessed. Since seller_id filtering was removed, the edit route now returns `200` and the delete route returns `200`. **Confirmed failing** — 1 failure in full test suite. Should be updated to reflect single-vendor behavior or removed.

#### 6. Orphan foreign key reference in test setup
`src/tests/test_product_search.py:48`: Product `p5` is created with `seller_id=2`, but only a seller with `id=1` exists in the test's `setup_db`. With SQLite this is silently ignored (FK enforcement disabled), but with PostgreSQL this would cause an `IntegrityError`.

#### 7. No CI/CD pipeline
No GitHub Actions, GitLab CI, or similar configuration exists. Tests must be run manually.

---

## Infrastructure & Operations

### Issues

- **No Dockerfile or docker-compose.yml**: No containerized development environment. Setup requires manual Python installation and dependency resolution.
- **No health check endpoint**: No `GET /health` or `GET /ready` for load balancers or orchestration.
- **No structured logging**: Uses `logging.basicConfig(level=logging.INFO)` with plain text format. No JSON logging for log aggregation tools.
- **No error tracking**: No Sentry, Rollbar, or similar integration. Errors are logged to stdout and lost on container restart.
- **No migration automation**: Alembic is configured (`alembic.ini`) but no migration scripts are present in the `migrations/` directory. The app relies on `SQLModel.metadata.create_all()` at startup, which is not safe for production schema changes.

---

## Detailed File Review

### `src/config.py`
- **Rating: 8/10**
- `SECRET_KEY` now has no default — crashes loudly if unset. Min-length validator (32 chars) enforced via `field_validator`.
- `extra="ignore"` silently swallows typos in `.env` — consider `extra="forbid"` for stricter validation.

### `src/database.py`
- **Rating: 4/10**
- `echo=True` must be removed or made configurable.
- No SSL enforcement on the connection string.
- No pool size limits.
- `get_session` is a generator function but typed as returning `AsyncSession` — should be `AsyncGenerator`.

### `src/middleware/csrf.py`
- **Rating: 5/10**
- Correct pattern but incomplete multipart support is a gap for the file upload forms.
- Cookie is set with `SameSite=Lax` but no `Secure` flag — cookies will be sent over HTTP.
- The `hmac` and `hashlib` imports are unused.

### `src/middleware/rate_limit.py`
- **Rating: 7/10**
- Sliding-window in-memory limiter with tiered rules: auth (5 POST/min), checkout (10 POST/min), global (120/min).
- `POST /checkout/` rule matches all product-specific checkout paths (`/checkout/{product_id}`) via `startswith` — prevents mass fake-order submissions.
- In-memory only — lost on process restart. A Redis-backed version is needed for multi-worker deployments.
- The global fallback (120 req/min per IP) applies to *all* paths including static assets. A request to `/auth/login` counts toward BOTH the auth-specific limit and the global limit due to the store key using the matched prefix.
- HTMX 429 responses use an emoji (`⏳`) which may not render in all contexts.

### `src/dependencies.py`
- **Rating: 7/10**
- `get_current_seller` refactored to extract `seller_id` from `request.session` directly instead of relying on an unresolved `Depends()` — allows dashboard routes to call it directly.
- `require_seller_id`, `require_current_seller` provide clean authorization gates.
- Still three distinct auth patterns across features (dependencies, dashboard, buyer) — consolidation in progress.

### `src/utils/crypto.py`
- **Rating: 6/10** (downgraded from 8)
- Correct use of Fernet with SHA-256 derived key.
- `decrypt_data` returns `"[encrypted]"` on failure, but **does not try `legacy_decrypt_data` as a fallback** — this is the biggest gap. Old encrypted records (seller phone, order buyer_phone, delivery_address) show `[encrypted]` throughout the app.
- `encrypt_data` on empty string returns the empty string — encrypted fields could be stored as empty strings without encryption.
- Key derivation uses domain separation via `derive_key(purpose)` — independently derived keys per purpose.
- `legacy_hash_data` / `legacy_decrypt_data` exist but are only used in `AuthService.get_seller_by_phone` (hash fallback) and the migration script, not in `decrypt_data`.
- **Fix**: `decrypt_data` should catch `InvalidToken` and try `legacy_decrypt_data` before returning `"[encrypted]"`.

### `src/utils/phone.py`
- **Rating: 8/10**
- Clean, well-documented, handles all Ethiopian phone formats.
- No international phone support (buyers outside Ethiopia would be rejected) — intentional per requirements.

### `src/utils/sms.py`
- **Rating: 6/10**
- `print()` statements on lines 54-56 and 61-64 leak SMS content (including OTP codes) to stdout. In production logs, this exposes OTPs. Use `logger.info()` or remove.
- `_dispatch_sms` creates a new `httpx.AsyncClient()` per call. In `send_order_notifications_sms` it uses one client for both, but `send_otp_sms` creates its own. Inconsistent pattern.

### `src/features/auth/routes.py`
- **Rating: 7/10**
- Clean code, good use of HTMX partial responses.
- The `get_login` route returns a 200 even when the user is already logged in — should redirect to `/dashboard`.

### `src/features/auth/services.py`
- **Rating: 7/10**
- OTP generation uses `secrets.randbelow` — secure.
- OTP verification correctly increments `attempts` and locks after 3 tries.
- No cleanup of expired OTP codes — the `otp_codes` table will grow unbounded.

### `src/features/products/models.py`
- **Rating: 7/10**
- Proper use of cascading deletes for images and attributes.
- `ProductTagLink` correctly models the many-to-many relationship.
- `price` uses `Decimal` with `decimal_places=2` and `gt=0` — good for financial data.

### `src/features/products/services.py`
- **Rating: 8/10**
- Methods renamed for single-vendor consistency: `get_seller_products` → `get_all_products`, `search_seller_products` → `search_products`, paginated variants similarly renamed.
- All `seller_id` WHERE clauses removed — product queries are no longer seller-scoped.
- `delete_product` uses soft-delete pattern correctly.
- Missing: batch operations, image cleanup on Cloudinary when deleting.

### `src/features/products/routes.py`
- **Rating: 7/10**
- Pagination added to `list_products`: accepts `page` param, uses paginated service methods, passes `current_page`/`total_pages` to template.
- Deprecated local `get_current_seller_id` — all routes now use `require_seller_id` from `src/dependencies`.
- Seller name and store name read from session instead of separate DB queries.
- Ownership checks (`product.seller_id != seller_id`) removed — single-vendor assumption.
- Overly long handlers (228 lines for `add_product`, 115 for `edit_product`).
- Image tag indices are 0-based from `form.getlist` but the existing image count from the edit form uses separate indexing — fragile.

### `src/features/dashboard/routes.py`
- **Rating: 6/10** (downgraded from 7)
- All `seller_id` filters removed from stats queries — single-vendor simplification.
- Order detail ownership check removed.
- Profile update correctly refreshes session name fields.
- **ORM mutated with plaintext**: `order.buyer_phone = decrypt_data(order.buyer_phone)` (line 107) writes decrypted phone back to the ORM object. Similarly `delivery_address` on line 108. If any subsequent code calls `commit()`, plaintext PII would be persisted. Currently safe but fragile.
- Profile route decrypts seller phone in-place: `seller.phone = f"+251{decrypt_data(seller.phone)}"` (line 174).
- Order list has **no pagination** (line 72-78) — fetches all orders without limit.
- Uses `get_current_seller()` called as a direct function rather than through `Depends()` — inconsistent with `products/routes.py` which uses `require_seller_id`.

### `src/features/orders/services.py`
- **Rating: 5/10** (downgraded from 6)
- Order ID generation has a race condition (see Design Patterns above).
- `seller_id` filter removed from the sequence count query (single-vendor).
- `NotificationService` handles both dict and ORM objects — unnecessary complexity.
- Background SMS task is fire-and-forget with no retry logic or delivery tracking.
- `generate_order_id` (line 108) fetches the entire `Seller` row from DB via `db.get(Seller, seller_id)` just to get `store_prefix`. Since `seller_name` and `store_name` are already in the session, `store_prefix` should also be stored there to avoid the DB hit on every order.
- `create_order` imports `normalize_phone` and `hash_data` inside the function body (lines 154, 170) — lazy imports that should be at module level.

### `src/scripts/migrate_seller.py`
- **Rating: 6/10**
- One-time script to create a duplicate seller record with the current encryption/hashing when `SECRET_KEY` changes break existing records.
- Uses `legacy_decrypt_phone` + `encrypt_phone` (new) + `hash_phone` (new) to re-encrypt/re-hash a known phone number.
- Hardcoded phone number — not reusable without editing.

### `src/features/buyer/routes.py`
- **Rating: 5/10** (downgraded from 6)
- Clean shop and checkout flow.
- Checkout POST (`process_checkout`) is rate-limited at 10 requests per 60 seconds per IP.
- **No CSRF protection on buyer-facing forms**: The checkout form at `buyer_checkout.html` doesn't include a CSRF token. The middleware would block the POST if the cookie doesn't match, but `process_checkout` uses FastAPI `Form(...)` which reads the body after the middleware passes — the middleware's form-data fallback (line 48-52 in csrf.py) only handles `application/x-www-form-urlencoded`, not `multipart/form-data`. Since buyer checkout sends URL-encoded data, this partially works, but the buyer page never explicitly sends the CSRF token.
- **ORM mutated with plaintext**: `order.buyer_phone = decrypt_data(order.buyer_phone)` (line 193) and `delivery_address` (line 194) in `order_confirmation` — same pattern as dashboard.
- `Seller` import at line 20-21 and line 197 is inside function bodies (lazy imports).
- `decrypt_data` import at line 191 is inside function body.
- `validate_ethiopian_phone` and `normalize_phone` imported at line 140 inside `process_checkout`.
- Phone normalization redundant in both route and service.

### `src/utils/storage.py`
- **Rating: 4/10**
- **Duplicated imports**: Lines 1-3 and 5-8 duplicate `import cloudinary`, `import cloudinary.uploader`, `from src.config import settings`, and `from urllib.parse import urlparse`. The second block at lines 5-8 is dead code that never executes.
- `CloudinaryService.delete_image` checks `if settings.CLOUDINARY_URL` (line 40) but `__init__` at line 35-39 calls `cloudinary.uploader.destroy` directly without checking — if Cloudinary is not configured, this raises an unhandled exception.
- `upload_image` raises `ValueError` if not configured — should be `RuntimeError` and should also be caught upstream.
- No error handling on `cloudinary.uploader.upload` — if the API call fails, the exception propagates to the route handler's `except Exception` catch-all.

### `src/utils/datetime.py`
- **Rating: 10/10**
- One function, one purpose, perfectly named, zero dependencies. A model of simplicity.

### `src/templates/` (overall)
- **Rating: 7/10**
- Consistent TailwindCSS styling with a custom color palette.
- HTMX partials are well-structured.
- TailwindCSS loaded via CDN — fine for development but should be bundled for production.
- Multiple `script` blocks scattered across templates should be consolidated.

---

## Priority Action Items

### Must fix before production

1. **Add legacy fallback to `decrypt_data`** — fall back to `legacy_decrypt_data` before returning `[encrypted]`. Without this, all existing PII (seller phone, order buyer_phone, delivery_address) shows as `[encrypted]` in the UI.
2. **Fix stale tests** — `test_edge_cases.py:test_cross_seller_protection` expects 404 for cross-seller access, but seller isolation was removed. Either remove or rewrite these tests.
3. **Fix orphan FK in test_product_search.py** — Product `p5` with `seller_id=2` needs a Seller with `id=2`.
4. **Remove `echo=True`** from database engine — make it configurable.
5. **Fix order ID race condition** — use a database sequence or `SELECT ... FOR UPDATE`.
6. **Remove `print()` from SMS service** — OTP codes must not appear in stdout logs.
7. **Add pagination to order list in dashboard** — current query has no limit.

### Should fix before production

8. Add `Secure` flag to CSRF cookie — or use `SameSite=Strict`.
9. Add SSL enforcement to database URL — append `?sslmode=require`.
10. Stop mutating ORM objects with plaintext — use separate template variables for decrypted data instead of overwriting encrypted fields.
11. Add seller registration/onboarding flow — new sellers currently cannot sign up through the app.
12. Consolidate `conftest.py` for test DRY.
13. Extract `delivery_fee` as a named constant (appears in `buyer/routes.py:100` and `orders/services.py:159`).
14. Add CI pipeline (GitHub Actions).
15. Add health check endpoint.
16. Centralize authorization logic — replace the three different auth patterns.
17. Add `Content-Security-Policy` header.
18. Add Sentry or similar error tracking.

### Nice to have

19. Extract shared template partials (`_product_card.html`).
20. Add repository layer for testability.
21. Redis-backed rate limiter.
22. Dockerize the application.
23. Add Alembic migration scripts instead of `create_all()`.
24. Bundle TailwindCSS (remove CDN dependency).
25. Store `store_prefix` in session to avoid the `db.get(Seller)` call in `generate_order_id`.
26. Add CSRF tokens to buyer checkout form.

---

## Conclusion

AleMart is a well-structured FastAPI application with thoughtful security decisions (encryption, rate limiting, CSRF, domain-separated key derivation) and a clean domain-driven layout. The HTMX + Jinja2 approach keeps the frontend simple and maintainable.

Recent improvements include:
- **`SECRET_KEY`** now has no default and is enforced via a min-length validator — crashes loudly if misconfigured.
- **Purpose-specific key derivation** — `derive_key()` produces independent keys for session signing, CSRF, encryption, and HMAC from the same master secret.
- **Seller product list pagination** — `get_seller_products_paginated` / `search_seller_products_paginated` added with `limit`/`offset`, 12 per page, HTMX pagination footer matches buyer shop.
- **`get_current_seller` refactored** — no longer relies on unresolved `Depends()` when called directly, fixing a login crash.
- **Seller sidebar data stored in session** — `seller_name` and `store_name` written to session at login, eliminating 8 redundant `SELECT Seller` queries per product route request.
- **Seller isolation removed** — all `seller_id` filters stripped from product, order, and dashboard queries for single-vendor operation. Ownership checks (`product.seller_id != seller_id`) removed.
- **Method names simplified** — `get_seller_products` → `get_all_products`, `search_seller_products` → `search_products`, etc.
- **Backward-compatible decrypt/hash** — `legacy_decrypt_data` and `legacy_hash_data` added to support existing DB records encrypted/hashed with pre-`derive_key` methods.

**New critical findings from June 2026 review:**
- `decrypt_data` lacks a legacy fallback — old encrypted records show `[encrypted]` throughout the app (dashboard, orders, profile).
- ORM objects are mutated with plaintext after decryption in both dashboard and buyer order routes — fragile and risky.
- Stale cross-seller protection tests will fail since seller isolation was removed.
- Test data has an orphan FK reference (`seller_id=2` without a seller 2).
- Buyer checkout page has no CSRF token in the form.
- No seller registration/onboarding path exists.
- `generate_order_id` fetches the entire seller row from DB just for the store prefix.

Remaining issues — including the legacy decrypt fallback, stale tests, database `echo=True`, order ID race condition, and `print()` in SMS service — still need addressing before production. The project needs **1-2 weeks** of focused work on the priority items above.

The codebase remains fundamentally healthy and the development patterns are sound. The recent single-vendor transition was executed cleanly, and the backward-compatible crypto functions provide a solid migration path. With the remaining gaps closed, this project has strong potential as a production e-commerce platform for Ethiopian sellers.

# AleMart Code Review

**Project:** Single-seller e-commerce platform for Ethiopian merchants  
**Stack:** FastAPI + PostgreSQL (SQLModel) + Jinja2 + HTMX + TailwindCSS  
**Date:** June 2026  
**Reviewer:** Senior Software Engineer

---

## Production Readiness Summary

The project is **approaching production readiness**. The core architecture is sound and all identified code-quality issues from earlier reviews have been resolved: legacy decrypt fallback, ORM plaintext mutation, SMS `print()` leak, CSRF `Secure` flag, test infrastructure, database `echo=True`, connection pooling, dead/lazy imports, repeated error handling, magic numbers, and inconsistent authorization patterns. The test suite has been fully migrated to a shared `conftest.py` and new coverage added for previously untested paths (rate limiter, CSRF middleware, checkout validation, image upload failures).

Remaining production-blocking gaps: order ID race condition, missing seller onboarding flow, and missing CI/CD. The project is at a **solid beta stage** — functional for demo/limited use, but requiring meaningful work before serving real customers.

**Estimated effort to production: 1-2 weeks** (assuming full-time work by one engineer).

---

## Ratings

| Area | Rating | Summary |
|------|--------|---------|
| **Security** | 7/10 | AES-256 at rest, derived keys per purpose, CSRF + rate limiting + OTP hardening. Remaining: no SSL on DB, no security headers, no email validation |
| **Performance** | 8/10 | Async throughout, selectinload eager loading, product pagination, connection pool limits configured. No caching |
| **Code Quality** | 8/10 | Clean domain separation, consistent naming, good type hints. All previously identified quality issues resolved |
| **Design Patterns** | 8/10 | Service layer, domain-driven structure, HTMX over SPA. Auth patterns unified. Remaining: order ID race condition, no repository layer |
| **Testing** | 8/10 | 95 tests passing across 18 files. Shared conftest adopted project-wide. Coverage: rate limiter, CSRF middleware, checkout validation, image upload failures. No CI |

**Overall: 8/10** — Solid beta. All initial review fixes applied, test infrastructure modernized. Remaining: order ID race condition, missing onboarding, no CI.

---

## Security

### Strengths

- **AES-256 encryption for PII**: Phone numbers and delivery addresses encrypted at rest via Fernet (AES-256) with per-field HMAC-SHA256 hashes for lookup (`src/utils/crypto.py:36-44`). Correct pattern — encrypt for confidentiality, hash for indexed lookups.
- **CSRF protection**: Custom middleware (`src/middleware/csrf.py`) protects all non-GET methods with token validation via cookie-header comparison. Cookie includes `SameSite=Lax` and conditional `Secure` flag.
- **Rate limiting**: Tiered sliding-window rate limiter (`src/middleware/rate_limit.py`) with stricter limits on auth endpoints (5 POST/min), checkout (10 POST/min), and global fallback (120/min).
- **OTP attempt limiting**: 3 attempts per OTP code (`src/features/auth/services.py:77`), 5-minute expiry, rate-limited to 5 OTP requests/hour.
- **Query parameterization**: All SQLAlchemy queries use parameterized `.where()` — no SQL injection risk.
- **Templates auto-escape**: Jinja2 auto-escaping via `{{ }}` prevents XSS.
- **Two-tier decrypt fallback**: `decrypt_data` tries current Fernet → legacy Fernet → `[encrypted]`, providing a clean migration path for records encrypted before the `derive_key` change.

### Issues

#### 1. No database connection encryption enforcement
`src/database.py` connects via `asyncpg`. No SSL/TLS enforcement (`?sslmode=require`). Database traffic (including PII) is transmitted in cleartext on unencrypted network paths.

#### 2. Email and address fields not validated
`Seller.business_email` is a plain `Optional[str]` with `max_length=255` — no email format validation. `delivery_address` is encrypted but never structurally validated. Malformed or excessively long inputs reach the database.

#### 3. Multipart CSRF relies on header/query fallback
CSRF middleware does not handle `multipart/form-data` bodies directly. Product forms pass the token as a query parameter (`?csrf_token=...`) which appears in server logs and browser history.

#### 4. No security headers
No `Content-Security-Policy`, `X-Frame-Options`, or `Strict-Transport-Security` set on responses.

---

## Performance

### Strengths

- **Eager loading via selectinload**: All product queries fetch images, attributes, and tags in fewer queries.
- **Async throughout**: FastAPI async handlers, async database sessions, async SMS HTTP calls.
- **Background SMS dispatch**: `orders/services.py` uses `asyncio.create_task()` for non-blocking notifications.
- **Connection pooling**: `pool_size=10`, `max_overflow=20` configured on the async engine.

### Issues

- No caching layer. Every product page hit queries the database.
- No image optimization strategy beyond Cloudinary defaults.

---

## Code Quality

### Strengths

- **Clean domain separation**: Features organized into `auth/`, `products/`, `orders/`, `buyer/`, `dashboard/` — each with own `routes.py`, `services.py`, `models.py`.
- **Consistent naming and type hints** throughout.
- **Service-layer pattern**: Business logic lives in service classes, not route handlers.
- **HTMX patterns consistent** across shop and product search pages.

### Issues

#### 1. No seller onboarding flow
New sellers cannot sign up through the application. They must be added manually via `src/scripts/add_seller.py` or direct DB insertion.

#### 2. Cross-feature coupling
`dashboard/routes.py` imports from `orders` and `products`; `buyer/services.py` imports from `products`. Not inherently wrong, but changes to one domain's models ripple through others.

#### 3. Templates duplicate partials
The product card HTML appears in `_product_list_content.html` and `_product_grid.html` — identical markup duplicated. Should be extracted to `products/_product_card.html`.

---

## Design Patterns

### Strengths

- **Service layer**: Business logic separated into service classes. Tests call services directly (e.g., `ProductService.search_products()`).
- **Domain-driven structure**: Features grouped by domain, not by layer.
- **HTMX over SPA**: Keeps backend simple and template-rendering consistent.
- **Soft deletes**: Products use `is_deleted` flag, preserving referential integrity.
- **Audit logging**: `OrderStatusLog` tracks every status change with old/new values, changed_by, and context.
- **Centralized auth**: All protected routes use `require_current_seller` or `require_seller_id` from `src/dependencies.py`.

### Issues

#### 1. Order ID generation race condition
`generate_order_id` at `orders/services.py:116-121` uses `SELECT COUNT(*)` to compute the next sequence number. Under concurrent requests, two orders could get the same ID. **Fix**: Use a database sequence, `SELECT ... FOR UPDATE`, or a distributed ID generator.

#### 2. No repository layer
Services construct SQLAlchemy queries directly. A repository layer would isolate ORM-specific code and speed up unit tests.

#### 3. Redundant DB hit for store prefix
`generate_order_id` fetches the entire `Seller` row just to get `store_prefix`. This value could be stored in the session (like `seller_name` and `store_name` already are).

---

## Testing

### Strengths

- **95 tests passing** across 18 files covering login, CSRF, products, orders, tags, profile, buyer search, edge cases, SMS, OTP, audit logging, checkout validation, CSRF middleware, rate limiter, and image upload failure paths.
- **Shared conftest.py** adopted by all test files — no per-file engine/sessionmaker/client boilerplate. Provides `client` (module-level `TestClient`), `maker` (async sessionmaker), `get_csrf_context()`, `seed_seller()`, `seller_id_override`, and `current_seller_override`.
- **File-based SQLite** (temp file, cleaned up post-session) for fast, isolated runs.
- **Service-layer and route-level tests** both present.
- **Test infrastructure fixed**: all authorization mock targets updated, unique `X-Forwarded-For` per test to prevent rate-limit collisions, orphan FK corrected.

### Issues

#### 1. No CI/CD pipeline
No GitHub Actions or similar configuration. Tests must be run manually.

---

## Infrastructure & Operations

### Issues

- **No Dockerfile or docker-compose.yml**: Setup requires manual Python installation.
- **No health check endpoint**: No `GET /health` or `GET /ready`.
- **No structured logging**: Plain text format. No JSON logging for aggregation.
- **No error tracking**: No Sentry or similar integration. Errors lost on restart.
- **No migration automation**: Alembic configured but no migration scripts. Relies on `create_all()` at startup, unsafe for production.

---

## Detailed File Review

### `src/constants.py` — **9/10**
Centralizes `MAX_IMAGE_SIZE` (5MB) and `DELIVERY_FEE` (150 ETB). Single source of truth.

### `src/config.py` — **8/10**
`SECRET_KEY` has no default — crashes loudly if unset. Min-length validator (32 chars). `extra="ignore"` swallows typos — consider `extra="forbid"`. Connection pool settings configurable via env vars.

### `src/database.py` — **8/10**
`echo=True` replaced with configurable `DATABASE_ECHO`. Pool limits added. No SSL enforcement. `get_session` typed as `AsyncSession` but returns a generator — should be `AsyncGenerator`.

### `src/middleware/csrf.py` — **7/10**
Correct cookie-header comparison pattern. `Secure` flag conditionally applied. Dead imports removed. Multipart forms rely on query-parameter fallback — token appears in logs/URL history.

### `src/middleware/rate_limit.py` — **7/10**
Sliding-window in-memory limiter with tiered rules. In-memory only — lost on restart. Requests to `/auth/login` count toward both the auth-specific limit AND the global fallback. HTMX 429 uses an emoji (`⏳`) which may not render everywhere.

### `src/dependencies.py` — **9/10**
`require_current_seller` and `require_seller_id` provide clean authorization gates. Auth patterns fully unified.

### `src/utils/crypto.py` — **8/10**
Correct Fernet + SHA-256 key derivation with domain separation. Two-tier decrypt fallback. `encrypt_data` on empty string returns empty — encrypted fields could be stored as empty strings.

### `src/utils/phone.py` — **8/10**
Clean, well-documented, handles all Ethiopian phone formats. No international support — intentional per requirements.

### `src/utils/sms.py` — **7/10**
`print()` replaced with `logger.info()`. Inconsistent client creation: `_dispatch_sms` creates a new `httpx.AsyncClient()` per call, but `send_order_notifications_sms` reuses one.

### `src/utils/storage.py` — **6/10**
Duplicate imports removed. `CloudinaryService.delete_image` checks config but `__init__` calls `cloudinary.uploader.destroy` without checking — raises unhandled exception if Cloudinary isn't configured. `upload_image` raises `ValueError` (should be `RuntimeError`). No error handling on the Cloudinary API call.

### `src/features/auth/routes.py` — **8/10**
Clean HTMX partial responses. `get_login` returns 200 when already logged in — should redirect to `/dashboard`. `post_login` always shows OTP page on SMS failure. Lazy imports moved to module level.

### `src/features/auth/services.py` — **7/10**
OTP generation uses `secrets.randbelow`. Verification increments `attempts` and locks after 3. No cleanup of expired OTP codes. `print()` for OTP codes in dev mode.

### `src/features/products/models.py` — **7/10**
Cascading deletes for images/attributes. Correct many-to-many via `ProductTagLink`. `price` uses `Decimal(places=2, gt=0)`.

### `src/features/products/services.py` — **8/10**
Methods renamed for single-vendor consistency. `seller_id` WHERE clauses removed. Soft-delete pattern. Missing: batch operations, Cloudinary image cleanup on delete.

### `src/features/products/routes.py` — **8/10**
Pagination on `list_products`. All routes use `require_seller_id`. Seller info read from session. Ownership checks removed (single-vendor). `_form_response()` helper deduplicates error handling. Magic numbers replaced. Image tag indexing is fragile (0-based `form.getlist` vs edit form's separate index).

### `src/features/dashboard/routes.py` — **8/10**
`seller_id` filters removed from stats. Order ownership check removed. Profile update refreshes session. ORM plaintext mutation fixed. All routes use `Depends(require_current_seller)`. Order list has **no pagination** — fetches all orders without limit.

### `src/features/orders/services.py` — **6/10**
Order ID has race condition. `seller_id` filter removed. `NotificationService` handles both dicts and ORM objects — unnecessary complexity. Background SMS fire-and-forget with no retry. `generate_order_id` fetches entire `Seller` row just for `store_prefix`. Lazy imports fixed. Magic number `Decimal("150.0")` replaced with `DELIVERY_FEE`.

### `src/features/buyer/routes.py` — **8/10**
Clean checkout flow. Checkout POST rate-limited at 10/min. CSRF token in form. ORM plaintext mutation fixed. Lazy imports moved to module level. Phone normalization redundant in both route and service.

### `src/utils/datetime.py` — **10/10**
One function, one purpose, zero dependencies.

### `src/templates/` — **7/10**
Consistent TailwindCSS styling. HTMX partials well-structured. Tailwind loaded via CDN — should be bundled for production. Multiple `script` blocks should be consolidated.

---

## Priority Action Items

### Must fix before production

1. **Fix order ID race condition** — use a database sequence or `SELECT ... FOR UPDATE`.
2. **Add pagination to order list in dashboard** — current query fetches all orders without limit.
3. **Add SSL enforcement to database URL** — append `?sslmode=require`.

### Should fix before production

4. Add seller registration/onboarding flow.
5. Add CI pipeline (GitHub Actions).
6. Add health check endpoint (`GET /health`).
7. Add `Content-Security-Policy` header.
8. Add Sentry or similar error tracking.

### Nice to have

9. Extract shared template partials (`_product_card.html`).
10. Add repository layer for testability.
11. Redis-backed rate limiter.
12. Dockerize the application.
13. Add Alembic migration scripts instead of `create_all()`.
14. Bundle TailwindCSS (remove CDN dependency).
15. Store `store_prefix` in session to avoid redundant `db.get(Seller)` call.

---

## Recent Fixes (June 2026)

All 24 issues identified in prior reviews have been resolved:

- **Security fixes**: Legacy decrypt fallback, ORM plaintext mutation eliminated, SMS `print()` leak closed, CSRF `Secure` flag, rate-limit test isolation.
- **Database fixes**: `echo=True` made configurable, connection pool limits added.
- **Code quality fixes**: Dead imports removed, lazy imports moved to module level, magic numbers centralized, repeated error handling deduplicated, dashboard auth unified.
- **Test infrastructure**: `pytest.ini` created, shared `conftest.py` adopted by all 18 test files, `client` changed from fixture to module-level global, SQLite switched from in-memory to file-based (resolved StaticPool + TestClient event-loop clash).
- **New coverage**: 13 tests added for checkout validation (4), CSRF middleware (4), rate limiter (2), and image upload failure paths (3).
- **Stale test removed**: `test_cross_seller_protection` deleted (single-vendor project).

**Result**: 95 tests passing — up from 8 failures before fixes.

---

## Conclusion

AleMart is a well-structured FastAPI application with thoughtful security decisions (encryption, rate limiting, CSRF, domain-separated key derivation) and a clean domain-driven layout. The HTMX + Jinja2 approach keeps the frontend simple and maintainable.

All 24 issues from the initial reviews are complete. The test suite runs 95 tests at 100% green with a modern shared conftest infrastructure and coverage across all major feature areas including the previously untested rate limiter, CSRF middleware, and image upload failure paths. Major code quality improvements — lazy imports, magic numbers, dead imports, repeated error blocks, and inconsistent auth patterns — have all been resolved.

The remaining production-blocking items — order ID race condition, missing onboarding flow, and no CI — each require focused effort but are individually scoped. The codebase remains fundamentally healthy and the development patterns are sound. With the remaining gaps closed, this project has strong potential as a production e-commerce platform for Ethiopian sellers.

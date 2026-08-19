# Session Summary (compacted)

## Objective
- Rebrand the site to "XCollections" (women's fashion) — rename branding, refresh buyer copy, replace prod catalog — **DONE + verified live**.
- Add a debug/demo cheat verification PIN (`199619`) bypassing OTP without skipping SMS and with no UI hint — **DONE + unit-tested** (user must add `AUTH_CHEAT_PIN=199619` to Vercel env vars).
- Keep the progress-bar UX; fix its integration with forms — **DONE, incl. a real bug found**.
- (Carry-over, blocked) grinev/opencode-telegram-bot bridge — awaiting bot token + numeric user ID (also depends on reinstalling `opencode-ai`; current `bin/opencode.exe` is a 479-byte error stub).

## Important Details
- Repo `https://github.com/lxfisseha/ecommerce-project-v1.git`; push to main → Vercel auto-deploy (~25–35 s). Live: `https://e-shop-eight-ochre.vercel.app`.
- Prod DB (5432 session pooler): `postgresql+asyncpg://postgres.rsrwyldsfcajuhjczjii:Nbo9iTw3scQVF8iX@aws-1-eu-central-1.pooler.supabase.com:5432/postgres` (gitignored `.env.production`). Seed/tag/rename scripts run with `$env:DATABASE_URL` from `.env.production` + `$env:PYTHONPATH = (Get-Location).Path`; PowerShell has no heredoc — use temp scripts under `C:\Users\JOY\AppData\Local\Temp\opencode\`.
- **AUTH_CHEAT_PIN=199619** is in `.env`/`.env.production` (gitignored). User MUST add it to Vercel env vars for the live demo. Behavior: `verify_otp` bypass via `hmac.compare_digest`, requires existing seller, marks pending OTPs used, SMS still sent, no UI hint. Login with non-existent phone still 404s before OTP.
- Static files served with `Cache-Control: public, max-age=31536000, immutable`; CSS is inlined in templates (no cache issue). **Any change to `/static/js/htmx-init.js` requires bumping the `?v=` query in `src/templates/base.html` (currently v6).**
- Progress bar final state: start 30%, height 4px; intercepts link clicks + plain form submits via `preventDefault → start() → double rAF → form.requestSubmit(submitter)`. **Fix: pass `e.submitter` to `requestSubmit()` so button-carried form data (e.g. `name="new_status"` on the order status form) survives — previously dropped, causing 422 "new_status Field required" on Mark as Shipped / Cancel Order.**
- Prod sellers: id=1 `XCollections` (DEMO prefix), id=3 `XCollections Demo` (DEMO_L prefix). `store_name` unique — bulk rename to same value fails with UniqueViolationError; rename per-id. Order refs look like `ET-DEMO_L-20260819-0009` (contains underscore).
- Prod catalog: 25 fashion products seeded from 21 templates; `seed_products.py --reset` deletes in FK-safe order (OrderStatusLog → OrderItem → Order → ProductTagLink → ProductImage → ProductAttribute → Product → Tag). All 21 Unsplash image URLs verified 200 (sandals image was replaced: `1600052448037-58da9b0f2a26` FAIL → `1591604466107-ec97de577aff`).
- Tailwind JIT pitfall: only classes present in JIT-compiled `output.css` work; verify before using new classes.
- Test commands: unit `python -m pytest src/tests -q -m "not e2e"` (**138 passed**). Local E2E `python -m pytest src/tests/e2e -m "e2e" --browser=chromium` (**46 passed**). Hosted E2E `$env:E2E_HOST_BASE_URL="https://e-shop-eight-ochre.vercel.app"` then same pytest (**31 passed, 15 skipped**). Uses Edge channel via conftest; local DB is seeded SQLite with the fashion catalog.
- PowerShell quirks: `$home` is a reserved/read-only variable (use e.g. `$resp`); no heredocs; git pathspecs should not be prefixed with `/`.

## Work State
### Completed
- Rebrand commit `510421f` (28 files): all template titles/brand text "Merchies"→"XCollections"; `main.py` title; `sms.py` messages+sender; `add_seller.py` store names; buyer copy (hero, search placeholder, `#Dresses`/`#Shoes`/`#Handbags` → `/shop?q=dress|shoes|handbag`, shop header "The Fashion Collection", product-detail terms line); `seed_products.py` rewritten (21 fashion templates, verified images, --reset FK-safe); `seed_tags.py` TAG_MAPPING; E2E title/h1 assertions + `test_buyer_search.py:36`.
- Cheat PIN commit `0761a23`: `AUTH_CHEAT_PIN: str = ""` in `src/config.py`, bypass in `verify_otp` (`services.py` imports `settings`), conftest autouse `_disable_cheat_pin`, `src/tests/test_cheat_pin.py` (5 tests). 138 unit tests green.
- Progress-bar fixes commits `79c13dd`…`3574cfc`: cache-busting + interception; `?v=5`.
- **Fix + E2E alignment commit `df73b5f` (pushed)**: submitter fix in `htmx-init.js` + `?v=6`; made buyer cart/direct-buy/browsing E2E catalog-agnostic (resolve product ids/prices dynamically via new `ShopPage.get_product_ids()`, `ProductPage.get_price()` filters `span.text-accent:has-text("ETB")` to avoid the header logo); added `skip_hosted` fixture + `place_order_and_wait()` in CheckoutPage; added 300 ms settle before `networkidle` in navigation helpers (the interceptor defers submit/navigation by 2 rAF frames, so `networkidle` returned before the action started); seeded local E2E DB with the fashion catalog (product 1 = "Elegant Maxi Dress" 2500 ETB, keeps the attribute-test total of 2750; tags Dresses/Shoes/Handbags/Accessories); updated seller-side product/dashboard assertions.
- Verified: unit 138 passed; local E2E 46 passed; hosted E2E 31 passed / 15 skipped; live pages show title "Welcome to XCollections", hero copy, tags, fashion product grid (12/page), product detail w/ seller name; live JS v6 serves the submitter fix.
- Prod DB: 25 fashion products + tags seeded; sellers renamed to XCollections / XCollections Demo.

### Blocked
- Telegram bridge: awaiting BotFather token + numeric user ID; depends on reinstalling `opencode-ai` (stub binary).
- (Deferred) re-add `statement_cache_size=0` in `src/database.py` to enable the 6543 transaction pooler — optional.

## Next Move
1. Ask user to add `AUTH_CHEAT_PIN=199619` to Vercel env vars (then the hosted seller login can be demoed live).
2. (When user provides token/ID) resume Telegram bridge setup.
3. Optionally run the local full E2E again after any future JS/template edits (the 300 ms settle + `wait_for_url`/`place_order_and_wait` patterns now guard against the interceptor's deferral race).

## Relevant Files
- `src/static/js/htmx-init.js`: submitter pass-through fix (v6).
- `src/templates/base.html`: `?v=6` script tag.
- `src/tests/e2e/pages/shop_page.py`: `get_product_ids()`; `product_page.py`: `get_price()`; `checkout_page.py`: `place_order_and_wait()` + 300 ms settle; `cart_page.py`/`home_page.py`: 300 ms settle before networkidle.
- `src/tests/e2e/conftest.py`: `skip_hosted` fixture, fashion seed (17 products incl. 2 out-of-stock), tags Dresses/Shoes/Handbags/Accessories.
- `src/tests/e2e/test_customer_{browsing,cart_flow,cart_management,direct_buy,attributes,seller_auth,seller_dashboard,seller_products}.py`: dynamic assertions + hosted skips.
- `src/scripts/seed_products.py`, `seed_tags.py`, `src/config.py`, `src/features/auth/services.py`, `src/tests/test_cheat_pin.py`, template files, `.env`/`.env.production` (gitignored).
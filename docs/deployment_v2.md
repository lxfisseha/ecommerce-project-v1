# Deployment Guide

Environment setup, configuration, and deployment instructions for XCollections.

---

## Architecture Overview

```
Browser ──► Caddy (TLS, :80/:443) ──► FastAPI (app:8000)
                                         │
                                         ├── Redis ──► RQ worker ──► Pillow
                                         │                          │
                                         │                   media_data volume
                                         │                   (originals + WebP variants)
                                         │
                                         └── PostgreSQL 17
                                                  │
                                                  └── AfroMessage API (SMS)
```

The app runs as Docker Compose services. Caddy terminates TLS and proxies to
the app, serving `/media/*` with immutable cache headers. Images live on the
`media_data` volume; a background worker generates 160/400/800 WebP variants
into the same volume.

No third-party image hosting is required.

---

## Prerequisites

| Service | Purpose | Required | Cost |
|---------|---------|----------|------|
| Docker Engine + Compose | Hosting | Yes | Free |
| AfroMessage account | SMS delivery | No (OTP falls back to Telegram) | Pay-per-SMS |

PostgreSQL, Redis, and the app image all ship as compose services.

---

## Step 1: Environment Variables

Create `.env` in the project root by copying `.env.example`:

```bash
cp .env.example .env
```

```env
# Required
SECRET_KEY=<32+ character random string>
POSTGRES_DB=xcollections
POSTGRES_USER=xcollections
POSTGRES_PASSWORD=<strong password>

# Images (defaults are correct for compose)
MEDIA_ROOT=/app/media
REDIS_URL=redis://redis:6379

# SMS (optional — omit to use Telegram-only OTP)
AFROMESSAGES_API_KEY=<your_api_key>
AFROMESSAGES_FROM=<sender_id>
```

### Generating SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

`DATABASE_URL` is composed by compose from the `POSTGRES_*` values, so you
do not set it by hand. The `+asyncpg` driver suffix is required for async
SQLModel sessions.

---

## Step 2: Database Setup

```bash
docker compose up -d postgres
docker compose exec app alembic upgrade head
```

Starting fresh:

```bash
docker compose exec app alembic downgrade base
docker compose exec app alembic upgrade head
```

If a database was created with `src/database.py`'s `init_db()` rather than
Alembic, there is no `alembic_version` row, so `alembic upgrade head` will
not apply anything. In that case either stamp it first
(`alembic stamp head`) or apply the schema changes by hand.

### Seed a store and sample data

```bash
docker compose exec app python src/scripts/add_seller.py
docker compose exec app python src/scripts/seed_products.py
```

`add_seller.py` creates the demo store and downloads its hero image into
local storage. `seed_products.py` downloads each sample image, stores it
locally, and queues variant generation.

---

## Step 3: Image Storage

Images are written to `MEDIA_ROOT`, which is the `media_data` Docker volume.
The volume is mounted into both `app` and `worker`; the worker cannot see
uploads if the two mount different paths.

On a fresh volume the app (uid 999) cannot write until ownership is fixed:

```bash
docker run --rm -v xcollections_media_data:/m caddy:2-alpine chown -R 999:999 /m
```

### How variants are produced

1. An upload writes `products/originals/<uuid>.<ext>` and commits the row.
2. `_enqueue_variants` queues an RQ job. This is best-effort: if Redis is
   unreachable the upload still succeeds.
3. The worker reads the original, resizes with Pillow, and writes
   `processed/products/<uuid>_{160,400,800}w.webp`, recording the keys in
   `product_images.processed_urls`.
4. Templates resolve images via the `media_url` filter, which picks the
   nearest generated width and falls back to the original while
   `processing_status` is not `completed`.

Re-run a single image after a fix:

```bash
docker compose exec app python -m src.scripts.process_images <image_id>
```

Backups: the volume lives at
`/var/lib/docker/volumes/xcollections_media_data/_data`, on the same disk as
the Postgres volume. Copy both off-host if you need disaster recovery;
neither is a backup on its own.

---

## Step 4: SMS Setup (Optional)

### AfroMessage

1. Register at [afiromessage.com](https://afiromessage.com)
2. Get an API key from the dashboard
3. Set `AFROMESSAGES_API_KEY` and `AFROMESSAGES_FROM` in `.env`

### Telegram Fallback

Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to `.env` for Telegram-based
OTP delivery.

If neither SMS nor Telegram is configured, OTP codes are logged to the
console (development only).

---

## Step 5: Deploy

```bash
# Build and start everything
docker compose up -d --build

# Confirm health
docker compose ps
```

Caddy requests a Let's Encrypt certificate on first start, so the domain must
already resolve to the host and ports 80/443 must be reachable. The site
block lives in `Caddyfile`; change the domain there and redeploy.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Session + encryption key |
| `POSTGRES_PASSWORD` | Database password |
| `MEDIA_ROOT` | Image storage root |
| `REDIS_URL` | RQ queue |
| `AFROMESSAGES_API_KEY` | SMS (optional) |
| `AFROMESSAGES_FROM` | SMS sender ID (optional) |
| `AUTH_CHEAT_PIN` | **Development only.** Skips OTP verification. Never set in production. |

---

## Step 6: Verify Deployment

1. `curl https://<your-domain>/health` returns `{"status":"ok",...}`
2. Login page renders
3. Log in with the seeded phone number
4. Dashboard loads with stats
5. Add a test product with an image
6. `docker compose logs worker` shows `Job OK`
7. `docker compose exec app sh -c 'ls /app/media/processed/products'` lists three `_160w`, `_400w`, `_800w` files
8. Open the shop page — the `<picture>` srcset should contain `/media/processed/...` URLs
9. `curl -I` one variant URL: expect `content-type: image/webp` and `cache-control: immutable`
10. Complete a test checkout and confirm the order appears in the dashboard

---

## Local Development

```bash
# Without Docker: no worker, so images stay as originals
pip install -r requirements.txt
alembic upgrade head
uvicorn src.main:app --reload --port 8765

# Tests (SQLite in-memory, no external services)
pytest src/tests/ -q
```

### Database Note

SQLite cannot be used for the running app because `src/database.py` sets
`statement_cache_size=0` (asyncpg-specific connect_arg). Tests work because
`conftest.py` overrides `connect_args`. For local development, use the
compose Postgres service.

---

## Production Checklist

- [ ] `SECRET_KEY` is a unique, cryptographically random string (32+ bytes)
- [ ] `POSTGRES_PASSWORD` is strong and not the example value
- [ ] `AUTH_CHEAT_PIN` is **empty**
- [ ] `media_data` volume is owned by uid 999 and mounted into both `app` and `worker`
- [ ] Disk has headroom for originals plus 3 variants per image
- [ ] Media and Postgres volumes are copied off-host
- [ ] AfroMessage sender ID is registered and approved
- [ ] Telegram bot token is configured as fallback
- [ ] Domain resolves to the host; Caddy obtained a certificate
- [ ] Rate limits are tuned for expected traffic (`RATE_LIMITS` in `src/middleware/rate_limit.py`). Current defaults: auth endpoints 5 POST/60s, checkout 30 POST/60s, global fallback 600/60s. Buyer-facing limits are kept high because Ethiopian carrier users often share public IPs (CGNAT).
- [ ] Session cookie `secure` flag is enabled (automatic when request.is_secure)
- [ ] Alembic migrations have been run against production database
- [ ] Seller account has been seeded with the correct phone number
- [ ] `docker compose logs worker` shows no repeated `Job Failed`

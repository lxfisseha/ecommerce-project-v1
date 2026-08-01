# Deployment Guide

Environment setup, configuration, and deployment instructions for StoreLedger.

---

## Architecture Overview

```
Browser ──► Vercel (serverless function)
                │
                ├── Cloudinary (image CDN)
                │
                └── Supabase PostgreSQL 16
                        │
                        └── AfroMessage API (SMS)
```

The app runs as a **Vercel serverless function** (ASGI via `versel.json` rewrites). Static assets (images) are served by Cloudinary. The database is Supabase PostgreSQL with asyncpg.

---

## Prerequisites

| Service | Purpose | Required | Cost |
|---------|---------|----------|------|
| Vercel account | Hosting | Yes | Free tier sufficient |
| Supabase account | PostgreSQL database | Yes | Free tier sufficient |
| Cloudinary account | Image hosting | Yes | Free tier (25GB storage) |
| AfroMessage account | SMS delivery | No (OTP falls back to Telegram) | Pay-per-SMS |

---

## Step 1: Environment Variables

Create `.env` in the project root:

```env
# Required
SECRET_KEY=<32+ character random string>
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:5432/<database>

# Cloudinary
CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>

# SMS (optional — skip to use Telegram-only OTP)
AFROMESSAGES_API_KEY=<your_api_key>
AFROMESSAGES_FROM=<sender_id>
```

### Generating SECRET_KEY

```python
python -c "import secrets; print(secrets.token_hex(32))"
```

### DATABASE_URL format

```
postgresql+asyncpg://postgres:password@db.example.supabase.co:5432/postgres
```

Note the `+asyncpg` driver suffix — required for async SQLModel sessions.

---

## Step 2: Database Setup

### Via Supabase Dashboard

1. Create a new Supabase project
2. Go to Project Settings → Database → Connection string
3. Copy the URI and add `+asyncpg` after `postgresql`
4. Paste into `.env` as `DATABASE_URL`

### Run Migrations

```bash
alembic upgrade head
```

If starting fresh:

```bash
alembic downgrade base
alembic upgrade head
```

### Seed Seller Account

```bash
python -c "from src.scripts.seed import seed_seller; seed_seller()"
```

This creates a seller with:
- Phone: `+251911111111`
- Store name: `Sample Store`

**Change these values in `src/scripts/seed.py` before seeding for production.**

---

## Step 3: Cloudinary Setup

1. Create a Cloudinary account
2. Copy the API environment variable from Dashboard
3. Set as `CLOUDINARY_URL` in `.env`

The app uses Cloudinary's `upload` API with tags (`image_tag` param) and `destroy` API for deletion. No special configuration needed.

---

## Step 4: SMS Setup (Optional)

### AfroMessage

1. Register at [afiroman.com](https://afiromessage.com)
2. Get API key from dashboard
3. Set `AFROMESSAGES_API_KEY` and `AFROMESSAGES_FROM` in `.env`

### Telegram Fallback

Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to `.env` for Telegram-based OTP delivery:

```env
TELEGRAM_BOT_TOKEN=<bot_token>
TELEGRAM_CHAT_ID=<chat_id>
```

If neither SMS nor Telegram is configured, OTP codes are logged to console (development only).

---

## Step 5: Deploy to Vercel

### Using Vercel CLI

```bash
# Install Vercel CLI
npm install -g vercel

# Log in
vercel login

# Deploy from project root
vercel --prod
```

### Using Git Integration

1. Push repo to GitHub/GitLab
2. Import project in Vercel dashboard
3. Set environment variables in Vercel project settings
4. Deploy

### versel.json

The `versel.json` rewrite rule maps all requests to `src/main.py`:

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/src/main.py" }]
}
```

### Vercel Environment Variables

Set these in Vercel project settings → Environment Variables:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Session + encryption key |
| `DATABASE_URL` | Supabase async connection string |
| `CLOUDINARY_URL` | Image hosting |
| `AFROMESSAGES_API_KEY` | SMS (optional) |
| `AFROMESSAGES_FROM` | SMS sender ID (optional) |

---

## Step 6: Verify Deployment

1. Visit `https://<your-app>.vercel.app`
2. Login page should render
3. Log in with the seeded phone number
4. Check dashboard loads with stats
5. Add a test product with image
6. Open shop page — product should appear
7. Complete a test checkout
8. Verify order appears in dashboard

---

## Local Development

### Without External Services

```bash
# Run without SMS (OTP logged to console)
uvicorn src.main:app --reload --port 8765

# Run tests (SQLite in-memory, no external services needed)
pytest src/tests/ -q
```

### Database Note

SQLite cannot be used for the running app because `src/database.py` sets `statement_cache_size=0` (asyncpg-specific connect_arg). Tests work because `conftest.py` overrides `connect_args`. For local development, use a local PostgreSQL instance or Supabase free tier.

---

## Production Checklist

- [ ] `SECRET_KEY` is a unique, cryptographically random string (32+ bytes)
- [ ] `DATABASE_URL` uses a production Supabase instance (not free tier for high traffic)
- [ ] Cloudinary account is on a paid tier if many images expected
- [ ] AfroMessage sender ID is registered and approved
- [ ] Telegram bot token is configured as fallback
- [ ] App is behind HTTPS (Vercel provides this by default)
- [ ] Rate limits are tuned for expected traffic (`RATE_LIMITS` in `src/middleware/rate_limit.py`). Current defaults: auth endpoints 5 POST/60s, checkout 30 POST/60s, global fallback 600/60s. Buyer-facing limits are kept high because Ethiopian carrier users often share public IPs (CGNAT).
- [ ] Session cookie `secure` flag is enabled (automatic when request.is_secure)
- [ ] Alembic migrations have been run against production database
- [ ] Seller account has been seeded with correct phone number

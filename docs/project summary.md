# Project Summary for AI Developer Agent

## Project Name
Ethiopia Single-Seller E-Commerce Platform (v1)

## Core Problem
Ethiopian sellers on Telegram/Instagram lack structured e-commerce tools → inefficient order management, poor buyer experience. This platform provides a digital storefront + order management system.

## Target Users
- **Seller** (e.g., Fanuel, 20–30 orders/month): Needs secure login, product listing, order dashboard, status updates.
- **Buyer** (e.g., Dawit): Needs product browsing, clear stock/price info, simple checkout, order confirmation.

## Key Success Metrics
- 50% reduction in manual inquiries
- Order completion time: <8 min (baseline 30 min)
- Zero missed orders
- Buyer satisfaction ≥4/5

---

## Functional Requirements (Simplified)

### Product Listing
- Seller can create/update product: name, description, price, multiple photos, stock status, size/color options
- "Sold out" items hidden from buyers; system prevents purchase

### Buyer Flow
- Grid + detailed product view
- Select quantity (1–10) & attributes → "Buy Now"
- Checkout: full name, phone (must be 09/07 + 10 digits), delivery address

### Orders
- Unique ID: `ET-[store prefix]-[YYYYMMDD]-[0001]`
- Confirmation page + SMS/Telegram message
- Order status: `pending → shipped → completed` (or `cancelled`). No backwards from completed/cancelled.

### Seller Dashboard
- Login: phone + OTP (SMS/Telegram), expires 5 min
- Orders table (oldest pending first)
- Click order → view details + change status
- Real-time notification on new order

---

## Non-Functional Requirements
- Product listing <3 sec on 3G; order submit <5 sec
- Supports 50 concurrent users
- Phone/address encrypted at rest (AES-256)
- Rate limits: 10 orders/min per buyer; 5 OTP requests/hour per number
- 99.5% availability
- Log all order status changes

---

## Tech Stack (Fixed)
- **Backend**: FastAPI (async)
- **Frontend**: Jinja2 templates + HTMX + TailwindCSS
- **Database**: PostgreSQL (Supabase free tier)
- **Image storage**: Cloudinary (free tier)
- **SMS**: Afromessages (free tier)
- **Hosting**: Render/Railway (free tier)

---

## Database Design (Key Entities)
- `Seller`: phone, store_name, store_prefix
- `Product`: name, description, price, in_stock, seller_id
- `ProductImage`: url, tag (main/thumbnail/gallery), product_id
- `ProductVariant`: size, color, product_id
- `Order`: order_id (custom format), buyer_name, buyer_phone, address, status, total, product_id, quantity, selected attributes
- `OTPCode`: phone, code, expires_at, used

---

## API/Route Structure (Selected)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /products | No | Buyer product grid (HTMX fragment) |
| POST | /orders | No | Submit order |
| POST | /login/otp | No | Request OTP |
| POST | /login/verify | No | Verify OTP, set session |
| GET | /dashboard | Yes | Seller dashboard |
| PATCH | /dashboard/orders/{id}/status | Yes | Update order status |
| POST | /dashboard/products | Yes | Create product |
| PUT | /dashboard/products/{id} | Yes | Update product |
| DELETE | /dashboard/products/{id} | Yes | Delete product |

> All dashboard routes require authentication. Session: `seller_session` HttpOnly cookie, 7 days.

---

## Out of Scope (Do NOT implement)
- Payment integration (Telebirr, Chapa, etc.)
- Automatic inventory deduction
- Multi-vendor marketplace
- Buyer login/registration
- Live chat/messaging
- Bulk product upload

---

## Development Phases
1. **Foundation** (Days 1–2): Project setup, DB, base templates
2. **Buyer Flow** (Days 2–7): Product pages, checkout, confirmation
3. **Seller Dashboard** (Week 2): OTP login, orders table, status updates
4. **Product Management** (Week 3): CRUD, image uploads, attributes
5. **Polish & Launch** (Week 3 end): Testing, deployment

---

## Key Constraints & Mitigations
- Use only **free tiers** (GitHub, Render, Supabase, Cloudinary)
- Compress images to <200KB; lazy loading
- Retry SMS on failure (3 attempts)
- Daily DB backups + CSV export for seller
- No domain needed for v1 (free subdomain)

---

## Testing Priorities
- Valid/invalid Ethiopian phone (09/07 + 10 digits)
- Order status flow (no backwards from completed/cancelled)
- OTP rate limiting (5/hour)
- Sold-out items not purchasable

---

## What You Should NOT Worry About (v1)
- Multi-tenancy
- Payments
- Buyer accounts
- Real-time chat
- Bulk uploads
- Amharic localization (English only)

---

**Start with Phase 1. Build buyer flow first, then dashboard.**
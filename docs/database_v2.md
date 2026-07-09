# Database Schema

Entity relationships, table schemas, and migration history for StoreLedger.

**Database:** PostgreSQL 16 via Supabase (asyncpg driver)
**ORM:** SQLModel (built on SQLAlchemy 2.0)
**Migrations:** Alembic (12 versions)

---

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Seller                                    │
│─────────────────────────────────────────────────────────────────────│
│ PK  id              UUID          (autogen)                         │
│     phone           VARCHAR(20)   UNIQUE, NOT NULL                  │
│     store_name      VARCHAR(100)  NOT NULL                          │
│     store_prefix    VARCHAR(10)   UNIQUE, NOT NULL                  │
│     display_name    VARCHAR(100)  NOT NULL                          │
│     telegram_id     VARCHAR(50)   NULLABLE                          │
│     created_at      TIMESTAMP     DEFAULT now()                     │
│     updated_at      TIMESTAMP     DEFAULT now(), on update now()    │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ 1
                          │
          ┌───────────────┼───────────────────────────────┐
          │               │                               │
          │ *             │ *                             │ *
          ▼               ▼                               ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
│     OtpCode      │ │     Product      │ │       Order          │
│──────────────────│ │──────────────────│ │──────────────────────│
│ PK  id     INT   │ │ PK  id     UUID  │ │ PK  id          INT  │
│ FK  seller_id     │ │ FK  seller_id    │ │ FK  product_id UUID  │
│     code         │ │     name         │ │ FK  seller_id  UUID  │
│     expires_at   │ │     description  │ │     customer_name    │
│     attempts     │ │     price        │ │     customer_phone   │
│     used         │ │     stock        │ │     address          │
│     created_at   │ │     is_active    │ │     quantity     INT │
└──────────────────┘ │     category     │ │     status      ENUM │
                      │     created_at   │ │     order_id   VARCHAR│
                      │     updated_at   │ │     created_at       │
                      └────────┬─────────┘ │     updated_at       │
                               │ 1         └──────────┬───────────┘
                               │                      │ 1
                    ┌──────────┼──────┐               │
                    │          │      │               │ *
                    │ *        │ *    │ *             ▼
                    ▼          ▼      ▼       ┌──────────────────────┐
        ┌──────────────┐ ┌────────────┐       │   OrderStatusLog    │
        │ ProductImage │ │ Product    │       │──────────────────────│
        │──────────────│ │ Attribute  │       │ PK  id          INT │
        │ PK  id  INT  │ │────────────│       │ FK  order_id    INT │
        │ FK  product  │ │ PK id  INT │       │     from_status     │
        │     image_url│ │ FK product │       │     to_status       │
        │     public_id│ │     brand   │       │     changed_by      │
        │     is_main  │ │     color   │       │     changed_at      │
        │     tag      │ │     size    │       └──────────────────────┘
        └──────────────┘ │     weight  │
                         └────────────┘
                               │
                               │ (many-to-many via link table)
                               │
                               ▼
               ┌────────────────────────────┐
               │     ProductTagLink         │
               │────────────────────────────│
               │ PK  id          INT        │
               │ FK  product_id  UUID       │
               │ FK  tag_id      INT        │
               │ UNIQUE (product_id, tag_id)│
               └────────────┬───────────────┘
                            │
                            │ *
                            ▼
                    ┌──────────────┐
                    │     Tag      │
                    │──────────────│
                    │ PK  id  INT  │
                    │     name     │
                    │     UNIQUE   │
                    └──────────────┘
```

---

## Table Schemas

### Seller

Stores merchant account information. One seller per deployment.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default uuid4 | Primary identifier |
| `phone` | VARCHAR(20) | UNIQUE, NOT NULL | Login identifier |
| `store_name` | VARCHAR(100) | NOT NULL | Display name on public pages |
| `store_prefix` | VARCHAR(10) | UNIQUE, NOT NULL | Used in order ID generation (e.g., `ET-{PREFIX}-...`) |
| `display_name` | VARCHAR(100) | NOT NULL | Seller's name |
| `telegram_id` | VARCHAR(50) | NULLABLE | Telegram chat ID for OTP fallback |
| `created_at` | TIMESTAMP | NOT NULL, default now() | |
| `updated_at` | TIMESTAMP | NOT NULL, default now() | Updated on profile edit |

---

### OtpCode

One-time passwords for authentication. Multiple codes can exist per seller (previous codes are marked `used` when new one is requested).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | |
| `seller_id` | UUID | FK → seller.id, NOT NULL | Owner of this OTP |
| `code` | VARCHAR(6) | NOT NULL | 6-digit code |
| `expires_at` | TIMESTAMP | NOT NULL | 5 minutes from creation |
| `attempts` | INTEGER | NOT NULL, default 0 | Maximum 3 attempts |
| `used` | BOOLEAN | NOT NULL, default FALSE | Soft invalidation on resend |
| `created_at` | TIMESTAMP | NOT NULL, default now() | |

---

### Product

Core product catalog entity.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default uuid4 | |
| `seller_id` | UUID | FK → seller.id, NOT NULL | Product owner |
| `name` | VARCHAR(200) | NOT NULL | Product title |
| `description` | TEXT | NOT NULL | Product description/Markdown |
| `price` | NUMERIC(10,2) | NOT NULL | Price in ETB |
| `stock` | INTEGER | NOT NULL, default 0 | Current stock count |
| `is_active` | BOOLEAN | NOT NULL, default TRUE | FALSE = hidden from buyers |
| `category` | VARCHAR(100) | NULLABLE | Product category |
| `created_at` | TIMESTAMP | NOT NULL, default now() | |
| `updated_at` | TIMESTAMP | NOT NULL, default now() | Updated on product edit |

---

### ProductImage

Product images hosted on Cloudinary.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | |
| `product_id` | UUID | FK → product.id, ON DELETE CASCADE | Parent product |
| `image_url` | VARCHAR(500) | NOT NULL | Cloudinary URL |
| `public_id` | VARCHAR(200) | NOT NULL | Cloudinary public_id (for deletion) |
| `is_main` | BOOLEAN | NOT NULL, default FALSE | Primary display image |
| `tag` | VARCHAR(100) | NULLABLE | Image tag for organization |

---

### ProductAttribute

Optional product attributes for additional detail.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | |
| `product_id` | UUID | FK → product.id, ON DELETE CASCADE | Parent product |
| `brand` | VARCHAR(100) | NULLABLE | |
| `color` | VARCHAR(50) | NULLABLE | |
| `size` | VARCHAR(50) | NULLABLE | |
| `weight` | NUMERIC(10,2) | NULLABLE | Weight in kg |

---

### Tag

Product tags for categorization and filtering.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | |
| `name` | VARCHAR(50) | UNIQUE, NOT NULL | Tag display name |

---

### ProductTagLink

Many-to-many join table for products and tags.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | |
| `product_id` | UUID | FK → product.id, ON DELETE CASCADE | |
| `tag_id` | INTEGER | FK → tag.id, ON DELETE CASCADE | |
| | | UNIQUE (product_id, tag_id) | Prevents duplicates |

---

### Order

Customer orders with encrypted PII.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | Internal ID |
| `product_id` | UUID | FK → product.id, NOT NULL | Ordered product |
| `seller_id` | UUID | FK → seller.id, NOT NULL | Order recipient |
| `customer_name` | VARCHAR(100) | NOT NULL | Buyer's name |
| `customer_phone` | TEXT | NOT NULL | AES-256-GCM encrypted |
| `address` | TEXT | NOT NULL | AES-256-GCM encrypted |
| `quantity` | INTEGER | NOT NULL, default 1 | 1–10 |
| `status` | VARCHAR(20) | NOT NULL, default 'pending' | Enum: pending/confirmed/shipped/delivered |
| `order_id` | VARCHAR(50) | UNIQUE, NOT NULL | Public reference: `ET-{prefix}-{YYYYMMDD}-{0001}` |
| `created_at` | TIMESTAMP | NOT NULL, default now() | |
| `updated_at` | TIMESTAMP | NOT NULL, default now() | Updated on status change |

---

### OrderStatusLog

Audit log for order status changes.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | |
| `order_id` | INTEGER | FK → order.id, NOT NULL | |
| `from_status` | VARCHAR(20) | NULLABLE | NULL for initial creation |
| `to_status` | VARCHAR(20) | NOT NULL | |
| `changed_by` | VARCHAR(100) | NOT NULL | Who made the change |
| `changed_at` | TIMESTAMP | NOT NULL, default now() | |

---

## Migration History

Alembic tracks 12 migration versions in `alembic/versions/`:

| Version | Description |
|---------|-------------|
| 001 | Initial schema — Seller, OtpCode |
| 002 | Add Product, ProductImage, ProductAttribute |
| 003 | Add Tag, ProductTagLink |
| 004 | Add Order, OrderStatusLog |
| 005 | Add store_prefix to Seller |
| 006 | Add order_id to Order |
| 007 | Add category to Product |
| 008 | Add telegram_id to Seller |
| 009 | Add tag to ProductImage |
| 010 | Update price precision |
| 011 | Add encryption columns |
| 012 | Add is_active to Product |

---

## Key Queries

### Dashboard Stats

```sql
SELECT
  (SELECT COUNT(*) FROM products WHERE seller_id = :sid) AS total_products,
  (SELECT COUNT(*) FROM orders WHERE seller_id = :sid AND status IN ('shipped', 'delivered')) AS sold_products,
  (SELECT COUNT(*) FROM products WHERE seller_id = :sid AND is_active = TRUE) AS active_products,
  (SELECT COUNT(*) FROM orders WHERE seller_id = :sid AND status = 'pending') AS pending_orders,
  (SELECT COUNT(*) FROM orders WHERE seller_id = :sid) AS total_orders;
```

### Order ID Generation (next sequence number)

```sql
SELECT COALESCE(MAX(CAST(SUBSTRING(order_id, '([0-9]+)$') AS INTEGER)), 0) + 1
FROM orders
WHERE order_id LIKE :pattern
  AND DATE(created_at) = CURRENT_DATE;
```

Pattern: `ET-{prefix}-{YYYYMMDD}-%`

### Product Search with Tags

```sql
SELECT p.* FROM products p
LEFT JOIN product_tag_link ptl ON p.id = ptl.product_id
LEFT JOIN tags t ON ptl.tag_id = t.id
WHERE p.is_active = TRUE
  AND p.seller_id = :sid
  AND (p.name ILIKE :search OR p.description ILIKE :search)
  AND (:tag IS NULL OR t.name = :tag)
ORDER BY p.created_at DESC
LIMIT 12 OFFSET :offset;
```

---

## Indexes

| Table | Index | Columns | Purpose |
|-------|-------|---------|---------|
| seller | idx_seller_phone | phone | Login lookup |
| seller | idx_seller_prefix | store_prefix | Order ID generation |
| otp_code | idx_otp_seller | seller_id | OTP lookup by seller |
| otp_code | idx_otp_active | seller_id, used, expires_at | Active OTP lookup |
| product | idx_product_seller | seller_id | Dashboard product list |
| product | idx_product_active | is_active | Shop display filter |
| product | idx_product_name | name | Shop search |
| product_tag_link | idx_ptl_product | product_id | Tag lookup |
| product_tag_link | idx_ptl_tag | tag_id | Products by tag |
| order | idx_order_seller | seller_id | Dashboard order list |
| order | idx_order_order_id | order_id | Confirmation page lookup |
| order | idx_order_status | seller_id, status | Dashboard status filter |
| order | idx_order_date | created_at | Order ID generation (daily) |
| order_status_log | idx_osl_order | order_id | Audit timeline |

Note: Indexes are inferred from query patterns and model definitions. Verify exact index definitions in actual migration files for production audit.

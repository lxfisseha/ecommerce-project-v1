-- Performance index + schema SQL (PostgreSQL)
-- This mirrors migrations/versions/5f3a9c21b7d0_add_performance_indexes_and_order_sequences.py
-- for environments where you prefer to run DDL directly instead of alembic upgrade.

-- 1. Common buyer-facing listing: active products, newest first.
CREATE INDEX IF NOT EXISTS ix_products_active_created
    ON products (in_stock, is_deleted, created_at DESC);

-- 2. Price sorting on the shop page (price-low / price-high).
CREATE INDEX IF NOT EXISTS ix_products_active_price
    ON products (in_stock, is_deleted, price);

-- 3. Recent-orders sort on the dashboard.
CREATE INDEX IF NOT EXISTS ix_orders_created_at
    ON orders (created_at);

-- 4. Home page hero picks the most recently updated seller.
CREATE INDEX IF NOT EXISTS ix_sellers_updated_at
    ON sellers (updated_at);

-- 5. Atomic per-(store_prefix, day) counter backing OrderService.generate_order_id.
CREATE TABLE IF NOT EXISTS order_sequences (
    id SERIAL PRIMARY KEY,
    store_prefix VARCHAR(10) NOT NULL,
    date VARCHAR(8) NOT NULL,
    seq INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_order_sequences_prefix_date UNIQUE (store_prefix, date)
);

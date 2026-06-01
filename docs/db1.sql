-- 1. sellers
CREATE TABLE sellers (
    id SERIAL PRIMARY KEY,
    store_name VARCHAR(100) NOT NULL UNIQUE,
    phone VARCHAR(15) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. otp_codes
CREATE TABLE otp_codes (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(15) NOT NULL,
    code VARCHAR(6) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_otp_phone_code ON otp_codes(phone, code);
CREATE INDEX idx_otp_expires_at ON otp_codes(expires_at);

-- 2. products
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    in_stock BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_products_seller_id ON products(seller_id);
CREATE INDEX idx_products_in_stock ON products(in_stock);

-- 3. product_images
CREATE TABLE product_images (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    image_url TEXT NOT NULL,
    image_tag VARCHAR(20) DEFAULT 'gallery',
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_product_images_product_id ON product_images(product_id);

-- 4. product_attributes
CREATE TABLE product_attributes (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    attribute_type VARCHAR(20) NOT NULL,
    attribute_value VARCHAR(50) NOT NULL,
    extra_price DECIMAL(10, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_product_attributes_product_id ON product_attributes(product_id);
CREATE UNIQUE INDEX idx_product_attributes_unique ON product_attributes(product_id, attribute_type, attribute_value);

-- 5. orders (simplified - no order_items)
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL UNIQUE,
    seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    buyer_name VARCHAR(100) NOT NULL,
    buyer_phone VARCHAR(15) NOT NULL,
    delivery_address TEXT NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id),
    product_name VARCHAR(200) NOT NULL,
    product_price DECIMAL(10, 2) NOT N  ULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 1 AND quantity <= 10),
    attributes_selected TEXT,
    subtotal DECIMAL(10, 2) NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    status_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_orders_seller_id ON orders(seller_id);
CREATE INDEX idx_orders_order_id ON orders(order_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at);
CREATE INDEX idx_orders_buyer_phone ON orders(buyer_phone);
ALTER TABLE orders ADD CONSTRAINT valid_status CHECK (status IN ('pending', 'shipped', 'completed', 'cancelled'));

-- 6. order_status_logs
CREATE TABLE order_status_logs (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    old_status VARCHAR(20),
    new_status VARCHAR(20) NOT NULL,
    changed_by VARCHAR(50) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_status_logs_order_id ON order_status_logs(order_id);
CREATE INDEX idx_status_logs_changed_at ON order_status_logs(changed_at);
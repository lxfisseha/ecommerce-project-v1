# API Reference

All endpoints return server-rendered HTML (no JSON API). Forms use `application/x-www-form-urlencoded`. CSRF token required on all mutating requests except file uploads.

---

## Public Routes (No Auth)

### GET `/`

Home page — displays the 8 most recently added products that are in stock.

```
Response: 200 — Rendered index.html
```

---

### GET `/shop`

Full product grid with search, sort, filter, and pagination.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `search` | string | — | Filter by product name (case-insensitive LIKE) |
| `sort` | enum | `newest` | `name_asc`, `name_desc`, `price_asc`, `price_desc`, `newest` |
| `tag` | string | — | Filter by tag name |
| `page` | int | `1` | Page number (12 items per page) |

```
Response: 200 — Rendered shop.html
```

**Example:** `GET /shop?search=shoe&sort=price_asc&tag=footwear&page=1`

---

### GET `/product/{product_id}`

Product detail page — images, attributes, tags, and "Buy Now" button.

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `product_id` | UUID | Product ID |

```
Response: 200 — Rendered product_detail.html
Response: 404 — Product not found or out of stock
```

---

### GET `/checkout/{product_id}`

Checkout form for a single product. Verifies the product exists and is in stock before rendering.

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `product_id` | UUID | Product ID |

```
Response: 200 — Rendered checkout.html
Response: 404 — Product not found or sold out
```

---

### POST `/checkout/{product_id}`

Place an order. Creates order record, sends SMS confirmation, redirects to confirmation page.

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `product_id` | UUID | Product ID |

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `customer_name` | string | Yes | Buyer name |
| `customer_phone` | string | Yes | Phone (encrypted at rest) |
| `address` | string | Yes | Delivery address (encrypted at rest) |
| `quantity` | int | Yes | 1–10 |
| `csrf_token` | string | Yes | CSRF token |

```
Response: 302 — Redirect to /order/{order_id}
Response: 422 — Validation error (rendered checkout.html with errors)
Response: 400 — Product sold out
Response: 429 — Too many requests (rate limit)
```

**CSRF:** Required (not multipart — this is URL-encoded form)

---

### GET `/order/{order_id}`

Order confirmation page — shows order details, order ID, and status.

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `order_id` | string | Order ID (format: `ET-{prefix}-{YYYYMMDD}-{0001}`) |

```
Response: 200 — Rendered order_confirmation.html
Response: 404 — Order not found
```

---

### POST `/auth/login`

Request an OTP code. Sends SMS to the seller's registered phone.

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `phone` | string | Yes | Phone number (must match registered seller) |
| `csrf_token` | string | Yes | CSRF token |

```
Response: 200 — Login page with "OTP sent" message
Response: 404 — Phone not registered
Response: 429 — Rate limit exceeded
```

---

### POST `/auth/verify-otp`

Verify OTP code and establish a session.

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `phone` | string | Yes | Phone number |
| `otp` | string | Yes | 6-digit code |
| `csrf_token` | string | Yes | CSRF token |

```
Response: 302 — Redirect to /dashboard (on success)
Response: 200 — Login page with error message (invalid/expired OTP)
Response: 429 — Rate limit exceeded
```

---

### POST `/auth/resend-otp`

Invalidate current OTP and send a new one.

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `phone` | string | Yes | Phone number |
| `csrf_token` | string | Yes | CSRF token |

```
Response: 200 — Login page with "New OTP sent" message
Response: 429 — Rate limit exceeded
```

---

### GET `/auth/logout`

Clear session and redirect to login page.

```
Response: 302 — Redirect to /auth/login
```

---

### GET `/support`

Static support/contact page.

```
Response: 200 — Rendered support.html
```

---

## Protected Routes (Auth Required — Seller)

All dashboard routes require a valid session. Unauthenticated requests receive a 302 redirect to `/auth/login`.

---

### GET `/dashboard`

Dashboard home — displays stats overview.

```
Response: 200 — Rendered dashboard.html
  Context:
  - total_products: int
  - sold_products: int
  - active_products: int
  - pending_orders: int
  - total_orders: int
```

---

### GET `/dashboard/orders`

Order list with search and status filter.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `search` | string | — | Search by customer name, phone, or order ID |
| `status` | enum | — | Filter: `pending`, `confirmed`, `shipped`, `delivered` |
| `page` | int | 1 | Page number |

```
Response: 200 — Rendered orders.html (with HTMX for search/filter)
```

---

### GET `/dashboard/orders/{order_id}`

Single order detail — customer info, product info, status timeline.

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `order_id` | int | Order primary key ID |

```
Response: 200 — Rendered order_detail.html
Response: 404 — Order not found
```

---

### POST `/dashboard/orders/{order_id}/status`

Update order status. Enforces state machine transitions.

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `order_id` | int | Order primary key ID |

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | enum | Yes | New status: `pending`, `confirmed`, `shipped`, `delivered` |
| `csrf_token` | string | Yes | CSRF token |

```
Response: 302 — Redirect to /dashboard/orders/{order_id}
Response: 400 — Invalid transition (e.g., pending → delivered)
```

**State machine rules:**

| From | To | Allowed |
|------|----|---------|
| pending | confirmed | Yes |
| confirmed | shipped | Yes |
| shipped | delivered | Yes |
| Any other transition | | No |

---

### GET `/dashboard/products`

Product list with stock status and management actions.

```
Response: 200 — Rendered products.html
```

---

### GET `/dashboard/products/add`

Product creation form.

```
Response: 200 — Rendered add_product.html
```

---

### POST `/dashboard/products/add`

Create a new product (multipart/form-data — file upload).

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Product name |
| `description` | string | Yes | Product description |
| `price` | decimal | Yes | Price in ETB |
| `stock` | int | Yes | Initial stock quantity |
| `category` | string | No | Product category |
| `tags` | string | No | Comma-separated tag names |
| `brand` | string | No | Brand attribute |
| `color` | string | No | Color attribute |
| `size` | string | No | Size attribute |
| `weight` | decimal | No | Weight attribute |
| `image` | file | No | Product image (Cloudinary upload) |
| `csrf_token` | string | Yes | CSRF token |

```
Response: 302 — Redirect to /dashboard/products
Response: 422 — Validation error (re-renders form)
```

**CSRF:** Exempt (multipart/form-data)

---

### GET `/dashboard/products/{product_id}/edit`

Product edit form — pre-filled with existing data.

```
Response: 200 — Rendered edit_product.html
Response: 404 — Product not found or not owned by seller
```

---

### POST `/dashboard/products/{product_id}/edit`

Update product details.

**Form Body:** Same as POST add (all fields optional for edit)

```
Response: 302 — Redirect to /dashboard/products
Response: 404 — Product not found or not owned
```

---

### POST `/dashboard/products/{product_id}/delete`

Delete a product and its Cloudinary images.

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `csrf_token` | string | Yes | CSRF token |

```
Response: 302 — Redirect to /dashboard/products
```

---

### POST `/dashboard/products/{product_id}/toggle-stock`

Toggle `is_active` flag (in stock / out of stock).

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `csrf_token` | string | Yes | CSRF token |

```
Response: 302 — Redirect to /dashboard/products
```

---

### POST `/dashboard/products/{product_id}/upload-image`

Upload additional product image to Cloudinary.

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | file | Yes | Image file |
| `tag` | string | No | Image tag for organization |

```
Response: 302 — Redirect to edit page
```

---

### POST `/dashboard/products/{product_id}/delete-image`

Delete a specific product image from Cloudinary and DB.

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image_id` | int | Yes | ProductImage ID |
| `csrf_token` | string | Yes | CSRF token |

```
Response: 302 — Redirect to edit page
```

---

### POST `/dashboard/products/{product_id}/set-main-image`

Set a product image as the main/primary display image.

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image_id` | int | Yes | ProductImage ID |
| `csrf_token` | string | Yes | CSRF token |

```
Response: 302 — Redirect to edit page
```

---

### GET `/dashboard/profile`

Seller profile form — pre-filled.

```
Response: 200 — Rendered profile.html
```

---

### POST `/dashboard/profile`

Update seller profile.

**Form Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `store_name` | string | Yes | Store display name |
| `store_prefix` | string | Yes | Store prefix for order IDs |
| `display_name` | string | Yes | Seller display name |
| `phone` | string | Yes | Phone number |
| `csrf_token` | string | Yes | CSRF token |

```
Response: 302 — Redirect to /dashboard/profile
Response: 422 — Validation error
```

---

## Error Responses

| Status | Meaning | Response |
|--------|---------|----------|
| 200 | Success | Rendered HTML template |
| 302 | Redirect | Location header (login, success, etc.) |
| 400 | Bad request | Error message in form |
| 401 | Unauthorized | Redirect to /auth/login |
| 403 | Forbidden | Redirect to /auth/login with message |
| 404 | Not found | Rendered 404.html |
| 422 | Validation error | Re-rendered form with errors |
| 429 | Rate limited | Plain text + Retry-After header |
| 500 | Server error | Rendered 500.html + logged traceback |

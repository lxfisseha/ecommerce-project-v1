# Feature Overview

This document describes every feature in the platform from a business and end-user perspective.

---

## 1. Passwordless Login (OTP via SMS)

**For the seller:** Log in using only your phone number — no passwords to remember or reset. Each login sends a one-time code (OTP) to your phone via SMS. Enter the code and you're in.

**How it works:**
- Enter your registered phone number on the login page
- An SMS with a 6-digit code is sent to your phone (with Telegram fallback)
- Enter the code to complete login
- Your session stays active for 7 days (or until you log out)
- For security, the system limits login attempts — too many requests in a short time will be temporarily blocked

**Behind the scenes:** The code expires after 5 minutes and can only be attempted 3 times before a new code is needed.

---

## 2. Seller Dashboard

A central command center for managing your entire store.

**Key sections:**

### 2a. Dashboard Home (Stats Overview)
- **Total products** — how many items are in your catalog
- **Sold products** — items that have been purchased
- **Active products** — items currently listed as in stock
- **Pending orders** — orders awaiting your action
- **Total orders** — all orders placed

### 2b. Product Management
Create, edit, and organize your product catalog:

- **Add products** with name, description, price, stock quantity, and category
- **Upload product images** — multiple images per product with Cloudinary hosting
- **Set product attributes** — brand, color, size, weight per item
- **Tag products** for easy categorization and filtering
- **Toggle stock status** — mark items as in stock or out of stock
- **Edit or delete** existing products at any time

### 2c. Order Management
Track and fulfill customer orders:

- View all orders with customer details (name, phone, delivery address)
- Search and filter orders
- Update order status through the lifecycle

### 2d. Profile Management
- Update your store name and display name
- Change your phone number

---

## 3. Order Lifecycle & Status Tracking

Every order follows a clear, trackable path from placement to delivery.

**Status flow:**

```
Pending → Confirmed → Shipped → Delivered
```

| Status | Meaning |
|--------|---------|
| **Pending** | Order placed, awaiting your review |
| **Confirmed** | You've reviewed and accepted the order — customer receives SMS notification |
| **Shipped** | Package dispatched to the customer |
| **Delivered** | Customer received the order |

**Why this matters:** Every status change is logged with a timestamp, creating an audit trail. If a customer asks "when was my order shipped?", you can see the exact time the status was updated.

---

## 4. Public Shop & Product Discovery

Your customers browse and discover products without needing an account.

### Home Page
- Displays the 8 most recently added products
- Clean, simple layout optimized for quick browsing

### Shop Page
- Full product catalog with **search** — find products by name
- **Sort options** — by name, price (low to high or high to low), or newest first
- **Tag filters** — click a tag to show only products with that tag
- **Pagination** — 12 products per page for fast loading
- **Responsive** — works on mobile phones, tablets, and desktops

### Product Detail Page
- Full product description
- Multiple product images with gallery view
- Product attributes (brand, color, size, weight)
- Tags for related browsing
- Clear "Buy Now" button linking directly to checkout

---

## 5. Anonymous Checkout

Customers can buy without creating an account or logging in — reducing friction and abandoned carts.

**Checkout flow:**
1. Customer clicks "Buy Now" on any product
2. They fill in their name, phone number, and delivery address
3. They place the order — no payment required at this stage
4. They receive an order confirmation page with their unique order reference

**Data protection:** Customer phone numbers and addresses are encrypted in the database (AES-256-GCM) — you can view them in the dashboard, but they're stored securely.

**One item at a time:** Each order contains one product. This keeps the checkout simple and fast.

---

## 6. Order Confirmation & Reference

Every order receives a unique, readable order ID visible to both you and the customer.

**Format:** `ET-{STORE}-{YYYYMMDD}-{0001}`

Example: `ET-MYES-20260709-0003`

The ID tells you: Ethiopian store, your store prefix, the date the order was placed, and a sequential number (resets daily). Both you and the customer can reference this ID in all communications.

---

## 7. SMS Notifications

Automated text messages keep customers informed.

| Event | Notification |
|-------|-------------|
| OTP code sent | SMS with 6-digit login code |
| Order confirmed | Customer receives confirmation with order details |

This keeps the customer in the loop and reduces the number of "has my order been placed?" inquiries.

---

## 8. Security Features

### CSRF Protection
All form submissions (except file uploads) are protected against cross-site request forgery. Every form includes a hidden token that the server validates before processing.

### Rate Limiting
The system automatically limits rapid requests to prevent abuse:

| Action | Limit |
|--------|-------|
| Login requests (OTP send) | 6 per minute |
| OTP verification | 1 per minute |
| Checkout submissions | 11 per minute |
| Other requests | 60 per minute |

When a limit is hit, the system tells the browser when to try again.

### Session Security
- Login sessions expire after 7 days of inactivity
- Session cookies are HttpOnly (inaccessible to JavaScript) and flagged as Secure when served over HTTPS

---

## 9. Responsive Design

The platform works on all devices:

- **Desktop**: Full sidebar navigation in the dashboard, wide product grids
- **Tablet & Mobile**: Collapsible navigation, single-column layouts, touch-friendly buttons
- The shop and checkout are optimized for mobile-first browsing

Built with **TailwindCSS** — fast, lightweight, and consistent across browsers.

---

## Out of Scope (by Design)

These features are intentionally omitted to keep the platform focused and simple:

| Feature | Reason |
|---------|--------|
| Shopping cart | Single-item checkout is simpler for the target market (phone-based buyers) |
| Payment gateway | Orders are fulfilled on delivery/cash-on-delivery basis |
| Buyer accounts | Anonymous checkout removes registration barriers |
| Multi-vendor | Single-seller platform per deployment |
| Buyer registration | Not needed for anonymous checkout model |

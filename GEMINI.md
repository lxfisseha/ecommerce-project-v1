# Ethiopia Single-Seller E-Commerce Platform (AleMart)

## Project Overview
A digital storefront and order management system for Ethiopian sellers on platforms like Telegram and Instagram. It aims to streamline order management and improve the buyer experience.

## Core Features
- **Seller Dashboard**: Secure login (OTP), order management (status updates), product CRUD.
- **Buyer Flow**: Product browsing (grid/detail), select attributes/quantity, checkout (validation for Ethiopian phone numbers), order confirmation.
- **Order Management**: Unique ID generation (`ET-[store prefix]-[YYYYMMDD]-[0001]`), status tracking (`pending → shipped → completed/cancelled`).

## Technology Stack
- **Backend**: FastAPI (Async)
- **Database**: PostgreSQL (SQLModel, Alembic)
- **Frontend**: Jinja2 + HTMX + TailwindCSS (via CDN)
- **Validation**: Pydantic
- **Security**: Passlib (bcrypt), OTP-based auth

## Directory Structure
- `src/main.py`: Entry point.
- `src/features/`: Domain-driven modular structure (auth, products, orders, dashboard).
- `src/templates/`: Global and feature-specific Jinja2 templates.
- `docs/`: Original requirement and architecture documents.

## Key Constraints & Rules
- **Phone Validation**: Must be Ethiopian format (starts with `09` or `07`, exactly 10 digits).
- **Order IDs**: Custom sequential format.
- **Status Flow**: No backward transitions once an order is `completed` or `cancelled`.
- **OTP**: Expires in 5 minutes; rate-limited to 5 requests per hour.

## Out of Scope (Do NOT implement in v1)
- Payment integration (Telebirr, Chapa, etc.)
- Automatic inventory deduction
- Multi-vendor marketplace
- Buyer login/registration
- Live chat/messaging
- Bulk product upload

## Database Entities
- `Seller`, `Product`, `ProductImage`, `ProductAttribute`, `Order`, `OtpCode`, `OrderStatusLog`.

## Installation
Install the following packages:
`fastapi, uvicorn, jinja2, python-multipart, sqlmodel, asyncpg, psycopg2-binary, python-dotenv, pydantic-settings, passlib[bcrypt]`

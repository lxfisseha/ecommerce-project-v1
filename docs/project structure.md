ecommerce/
│
├── src/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Settings, env variables
│   ├── database.py             # DB connection engine
│   │
│   ├── shared/                 # Shared utilities (NOT a feature)
│   │   ├── __init__.py
│   │   ├── dependencies.py     # Common dependencies (get_db, require_auth)
│   │   ├── utils.py            # Phone validation, order ID generation
│   │   └── models.py           # Base SQLAlchemy model class
│   │
│   ├── features/
│   │   │
│   │   ├── products/           # FEATURE: Product catalog
│   │   │   ├── __init__.py
│   │   │   ├── router.py       # API endpoints (GET /products, /products/{id})
│   │   │   ├── models.py       # Product, ProductImage, ProductAttribute
│   │   │   ├── schemas.py      # Pydantic (CreateProduct, UpdateProduct)
│   │   │   ├── service.py      # Business logic (create_product, get_products)
│   │   │   └── templates/
│   │   │       ├── product_list.html
│   │   │       └── product_detail.html
│   │   │
│   │   ├── orders/             # FEATURE: Order processing
│   │   │   ├── __init__.py
│   │   │   ├── router.py       # POST /orders, GET /orders/{order_id}
│   │   │   ├── models.py       # Order, OrderStatusLog
│   │   │   ├── schemas.py      # CreateOrderRequest, OrderResponse
│   │   │   ├── service.py      # create_order, validate_phone, generate_order_id
│   │   │   └── templates/
│   │   │       ├── checkout_form.html
│   │   │       └── order_confirmation.html
│   │   │
│   │   ├── auth/               # FEATURE: Seller authentication
│   │   │   ├── __init__.py
│   │   │   ├── router.py       # GET /login, POST /login/otp, POST /login/verify, POST /logout
│   │   │   ├── models.py       # Seller, OtpCode
│   │   │   ├── schemas.py      # LoginRequest, OtpRequest, OtpVerifyRequest
│   │   │   ├── service.py      # generate_otp, send_sms, verify_otp, create_session
│   │   │   └── templates/
│   │   │       ├── login.html
│   │   │       └── otp_form.html
│   │   │
│   │   ├── dashboard/          # FEATURE: Seller dashboard
│   │   │   ├── __init__.py
│   │   │   ├── router.py       # GET /dashboard, PATCH /dashboard/orders/{id}/status
│   │   │   ├── service.py      # get_dashboard_orders, update_order_status
│   │   │   └── templates/
│   │   │       ├── dashboard.html
│   │   │       └── partials/
│   │   │           ├── orders_table.html
│   │   │           └── order_status_cell.html
│   │   │
│   │   └── seller_products/    # FEATURE: Seller product management (separate from buyer products)
│   │       ├── __init__.py
│   │       ├── router.py       # GET /dashboard/products, POST /dashboard/products, DELETE /dashboard/products/{id}
│   │       ├── service.py      # create_product, update_product, delete_product, upload_image
│   │       └── templates/
│   │           ├── product_list_manage.html
│   │           ├── product_form.html
│   │           └── image_gallery.html
│   │
│   ├── static/                 # Global static files (shared across features)
│   │   ├── css/
│   │   │   └── custom.css      # Only if needed (Tailwind is CDN)
│   │   └── js/
│   │       └── htmx-extras.js  # Optional HTMX extensions
│   │
│   └── templates/              # Global templates (base layout only)
│       ├── base.html           # Shared layout for all pages
│       └── partials/
│           ├── header.html
│           ├── footer.html
│           └── error.html
│
├── tests/
│   ├── __init__.py
│   ├── test_products.py
│   ├── test_orders.py
│   ├── test_auth.py
│   └── conftest.py             # Shared fixtures
│
├── .env                        # Environment variables
├── .gitignore
├── requirements.txt
├── alembic.ini                 # Migration config
└── README.md
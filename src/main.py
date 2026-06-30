from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from src.middleware.csrf import CustomCSRFMiddleware
from src.middleware.rate_limit import RateLimitMiddleware
from src.config import settings
from src.utils.crypto import derive_key
from src.templates_config import templates
from src.features.auth.routes import router as auth_router
from src.features.dashboard.routes import router as dashboard_router
from src.features.products.routes import router as products_router
from src.features.buyer.routes import router as buyer_router  # New import
from sqlalchemy.exc import SQLAlchemyError
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AleMart Merchant Solution Center",
    docs_url=None,  # Disable Swagger UI
    redoc_url=None,  # Disable ReDoc
    openapi_url=None,
)

# Middleware stack (applied in reverse order — last added runs first)
# Each middleware gets a purpose-specific key derived from the master SECRET_KEY
app.add_middleware(SessionMiddleware, secret_key=derive_key("session"))
app.add_middleware(
    CustomCSRFMiddleware,
    secret=derive_key("csrf"),
)
app.add_middleware(RateLimitMiddleware)


# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = "An unexpected error occurred. Please try again later."

    if isinstance(exc, SQLAlchemyError):
        logger.error(f"Database error: {exc}")
        error_msg = "We're having trouble connecting to our services. Please refresh the page in a moment."
    else:
        logger.error(f"System error: {exc}")

    return templates.TemplateResponse(
        request,
        "error.html",
        {"request": request, "error_message": error_msg},
        status_code=500,
    )


# Include routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
app.include_router(products_router, prefix="/dashboard/products", tags=["products"])
app.include_router(buyer_router, tags=["buyer"])  # New router for buyer-facing pages


@app.get("/")
async def root_redirect():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(
        url="/"
    )  # Redirect to buyer homepage (handled by buyer_router)

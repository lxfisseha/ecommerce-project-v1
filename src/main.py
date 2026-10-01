from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
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
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager with startup validation."""
    # Startup validation
    _validate_startup_config()
    logger.info("Startup validation passed")
    yield
    # Shutdown
    logger.info("Application shutdown")


def _validate_startup_config() -> None:
    """Validate critical configuration at startup. Fail fast if critical config is missing."""
    errors: list[str] = []
    warnings: list[str] = []

    # Critical: Required for core functionality
    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        errors.append("SECRET_KEY must be at least 32 characters")

    if not settings.DATABASE_URL:
        errors.append("DATABASE_URL is required")

    # Critical: Auth/SMS
    if not settings.AFROMESSAGES_API_KEY:
        errors.append("AFROMESSAGES_API_KEY is required for OTP SMS")

    # Images are stored on the local filesystem
    if not settings.MEDIA_ROOT:
        errors.append("MEDIA_ROOT is required for local image storage")

    # Optional: Cheat PIN (should be empty in production)
    if settings.AUTH_CHEAT_PIN:
        warnings.append("AUTH_CHEAT_PIN is set - disable in production")

    # Report warnings
    for w in warnings:
        logger.warning(f"Config warning: {w}")

    # Fail fast on errors
    if errors:
        logger.error("Startup validation failed:")
        for e in errors:
            logger.error(f"  - {e}")
        sys.exit(1)


app = FastAPI(
    title="XCollections Merchant Solution Center",
    docs_url=None,  # Disable Swagger UI
    redoc_url=None,  # Disable ReDoc
    openapi_url=None,
    lifespan=lifespan,
)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")


class CachedStaticFiles(StaticFiles):
    """Static files are referenced with versioned query strings (?v=...), so they
    can be cached immutably. ETag/Last-Modified revalidation still applies to
    any unversioned request."""

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app.mount("/static", CachedStaticFiles(directory=static_dir), name="static")


# Middleware stack (applied in reverse order — last added runs first)
# Each middleware gets a purpose-specific key derived from the master SECRET_KEY
app.add_middleware(SessionMiddleware, secret_key=derive_key("session"))
app.add_middleware(
    CustomCSRFMiddleware,
    secret=derive_key("csrf"),
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)


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


@app.get("/health")
async def health_check():
    """Health check with dependency verification."""
    from src.database import async_session_maker
    from sqlalchemy import text
    from src.config import settings

    # Check database connectivity
    db_ok = False
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        logger.error(f"Health check DB failed: {e}")

    # Check critical config
    config_ok = bool(settings.AFROMESSAGES_API_KEY and settings.SECRET_KEY and settings.DATABASE_URL)

    return {
        "status": "ok" if db_ok and config_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "config": "complete" if config_ok else "incomplete",
    }


@app.get("/")
async def root_redirect():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(
        url="/"
    )  # Redirect to buyer homepage (handled by buyer_router)

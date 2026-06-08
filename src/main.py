from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from src.middleware.csrf import CustomCSRFMiddleware
from src.config import settings
from src.templates_config import templates
from src.features.auth.routes import router as auth_router
from src.features.dashboard.routes import router as dashboard_router
from src.features.products.routes import router as products_router
from src.features.buyer.routes import router as buyer_router # New import

app = FastAPI(title="AleMart Merchant Solution Center")

# Middleware stack
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(
    CustomCSRFMiddleware,
    secret=settings.SECRET_KEY,
)

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return templates.TemplateResponse(
        request,
        "error.html",
        {"request": request, "error_message": str(exc)},
        status_code=500
    )

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
app.include_router(products_router, prefix="/dashboard/products", tags=["products"])
app.include_router(buyer_router, tags=["buyer"]) # New router for buyer-facing pages


@app.get("/")
async def root_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/") # Redirect to buyer homepage (handled by buyer_router)

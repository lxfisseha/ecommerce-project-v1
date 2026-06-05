from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from src.middleware.csrf import CustomCSRFMiddleware
from src.features.auth.routes import router as auth_router
from src.templates_config import templates
from src.config import settings
import os

app = FastAPI(title="AleMart Merchant Solution Center")

# Middleware stack
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(
    CustomCSRFMiddleware,
    secret=settings.SECRET_KEY,
)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])

@app.get("/")
async def root(request: Request):
    # For now, redirect or show a basic landing, but let's just point to login
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/auth/login")

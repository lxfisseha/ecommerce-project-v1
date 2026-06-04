from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from src.features.auth.routes import router as auth_router
import os

app = FastAPI(title="AleMart Merchant Solution Center")

# Templates configuration
templates = Jinja2Templates(directory="src/templates")

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])

@app.get("/")
async def root(request: Request):
    # For now, redirect or show a basic landing, but let's just point to login
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/auth/login")

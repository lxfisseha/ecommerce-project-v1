from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="src/templates")

@router.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="auth/login.html"
    )

@router.post("/login")
async def post_login(request: Request, phone: str = Form(...)):
    # This is where the HTMX request from login.html will land
    # For now, we'll just return a placeholder or the next step (OTP)
    # Since login.html expects a swap, we could return a small partial or a success message
    return HTMLResponse(content=f"<p class='text-green-600'>OTP sent to {phone}!</p>")

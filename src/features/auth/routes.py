from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.templates_config import templates
from src.database import get_session
from .services import AuthService, validate_ethiopian_phone

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    template_name = "auth/login_partial.html" if request.headers.get("HX-Request") else "auth/login.html"
    return templates.TemplateResponse(
        request=request, 
        name=template_name
    )

@router.post("/login")
async def post_login(
    request: Request, 
    phone: str = Form(...), 
    db: AsyncSession = Depends(get_session)
):
    # 1. Validate phone format
    if not validate_ethiopian_phone(phone):
        return templates.TemplateResponse(
            request=request,
            name="auth/login_partial.html",
            context={"error": "Invalid phone number. Use 9 or 7 followed by 8 digits.", "phone": phone},
            status_code=422
        )

    # 2. Check if seller exists
    seller = await AuthService.get_seller_by_phone(db, phone)
    if not seller:
        return templates.TemplateResponse(
            request=request,
            name="auth/login_partial.html",
            context={"error": "No seller found with this phone number. Please register first.", "phone": phone},
            status_code=404
        )

    # 3. Generate and Save OTP
    await AuthService.generate_otp(db, phone)

    # 4. Return the OTP verification partial
    return templates.TemplateResponse(
        request=request,
        name="auth/otp_partial.html",
        context={"phone": phone}
    )

@router.post("/verify-otp")
async def post_verify_otp(
    request: Request,
    phone: str = Form(...),
    code: str = Form(...),
    db: AsyncSession = Depends(get_session)
):
    # 1. Verify OTP
    result = await AuthService.verify_otp(db, phone, code)
    if not result["success"]:
        # We need to render the otp_partial.html again with the error
        return templates.TemplateResponse(
            request=request,
            name="auth/otp_partial.html",
            context={"phone": phone, "error": result["message"]},
            status_code=400
        )

    # 2. Get Seller
    seller = await AuthService.get_seller_by_phone(db, phone)
    if not seller:
        return templates.TemplateResponse(
            request=request,
            name="auth/otp_partial.html",
            context={"phone": phone, "error": "Seller not found."},
            status_code=404
        )

    # 3. Set Session
    request.session["seller_id"] = seller.id

    # 4. Redirect
    return HTMLResponse(
        content="<p class='text-green-600'>Login successful! Redirecting...</p>",
        headers={"HX-Redirect": "/dashboard"}
    )

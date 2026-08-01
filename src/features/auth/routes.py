from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.templates_config import templates
from src.database import get_session
from .services import AuthService
from src.utils.phone import validate_ethiopian_phone

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    template_name = "auth/login_partial.html" if request.headers.get("HX-Request") else "auth/login.html"
    return templates.TemplateResponse(request, template_name, {"request": request})

@router.post("/login")
async def post_login(
    request: Request, 
    db: AsyncSession = Depends(get_session)
):
    form = getattr(request.state, "form_data", None) or await request.form()
    phone = form.get("phone")

    # 1. Validate phone format
    if not phone or not validate_ethiopian_phone(phone):
        return templates.TemplateResponse(
            request,
            "auth/login_partial.html",
            {"request": request, "error": "Invalid phone number. Use 9 or 7 followed by 8 digits.", "phone": phone},
            status_code=422
        )

    # 2. Check if seller exists
    seller = await AuthService.get_seller_by_phone(db, phone)
    if not seller:
        return templates.TemplateResponse(
            request,
            "auth/login_partial.html",
            {"request": request, "error": "No seller found with this phone number. Please register first.", "phone": phone},
            status_code=404
        )

    # 3. Generate and Save OTP
    await AuthService.generate_otp(db, phone)

    # 4. Return the OTP verification partial
    return templates.TemplateResponse(
        request,
        "auth/otp_partial.html",
        {"request": request, "phone": phone}
    )

@router.post("/verify-otp")
async def post_verify_otp(
    request: Request,
    db: AsyncSession = Depends(get_session)
):
    form = getattr(request.state, "form_data", None) or await request.form()
    phone = form.get("phone")
    code = form.get("code")

    # 1. Verify OTP
    result = await AuthService.verify_otp(db, phone, code)
    if not result["success"]:
        # We need to render the otp_partial.html again with the error
        return templates.TemplateResponse(
            request,
            "auth/otp_partial.html",
            {"request": request, "phone": phone, "error": result["message"]},
            status_code=400
        )

    # 2. Get Seller (already fetched by verify_otp — no redundant re-query)
    seller = result.get("seller")
    if not seller:
        return templates.TemplateResponse(
            request,
            "auth/otp_partial.html",
            {"request": request, "phone": phone, "error": "Seller not found."},
            status_code=404
        )

    # 3. Clear old session and regenerate (prevents session fixation)
    request.session.clear()
    request.session["seller_id"] = seller.id
    request.session["seller_name"] = f"{seller.first_name} {seller.last_name}"
    request.session["store_name"] = seller.store_name

    # 4. Redirect
    return HTMLResponse(
        content="<p class='text-green-600'>Login successful! Redirecting...</p>",
        headers={"HX-Redirect": "/dashboard"}
    )

@router.post("/resend-otp")
async def post_resend_otp(
    request: Request,
    db: AsyncSession = Depends(get_session)
):
    form = getattr(request.state, "form_data", None) or await request.form()
    phone = form.get("phone")

    if not phone or not validate_ethiopian_phone(phone):
        return templates.TemplateResponse(
            request,
            "auth/otp_partial.html",
            {"request": request, "phone": phone, "error": "Invalid phone number."},
            status_code=422
        )

    await AuthService.generate_otp(db, phone)

    return templates.TemplateResponse(
        request,
        "auth/otp_partial.html",
        {"request": request, "phone": phone}
    )

@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=303)
